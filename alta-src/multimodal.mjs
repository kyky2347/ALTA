const KIMI_IMAGE_MIMES = new Set([
  "image/bmp",
  "image/gif",
  "image/heic",
  "image/heif",
  "image/jpeg",
  "image/png",
  "image/webp",
]);
const KIMI_VIDEO_MIMES = new Set([
  "video/3gpp",
  "video/avi",
  "video/mp4",
  "video/mov",
  "video/mpeg",
  "video/mpg",
  "video/webm",
  "video/wmv",
  "video/x-flv",
]);
const DEEPSEEK_IMAGE_MIMES = new Set([
  "image/gif",
  "image/jpeg",
  "image/png",
  "image/webp",
]);
const XAI_IMAGE_MIMES = new Set(["image/jpeg", "image/png"]);
const AUDIO_TOKENS_PER_SECOND = 50;
const DEEPSEEK_IMAGE_TOKEN_COST = 384;
const IMAGE_TOKEN_COST = 2_500;
const MAX_AUDIO_SECONDS = 180;
const MAX_MEDIA_TOKENS = 9_000;
const PROVIDER_FILE_TOKEN_COST = 6_000;
const TEXT_PREVIEW_TOKEN_COST = 900;
const VIDEO_TOKEN_COST = 5_500;
const CURRENT_INPUT_TYPES = new Set([
  "agent_message",
  "custom_tool_call_output",
  "function_call_output",
  "message",
]);
const TEXT_FILE_MIMES = new Set([
  "application/json",
  "application/xml",
  "text/csv",
  "text/html",
  "text/markdown",
  "text/plain",
  "text/xml",
]);

function multimodalError(message, code) {
  return Object.assign(new Error(message), {
    status: 400,
    code,
    retryable: false,
  });
}

function dataUrl(value) {
  if (typeof value !== "string" || !value.startsWith("data:")) return null;
  const comma = value.indexOf(",");
  if (comma < 6)
    throw multimodalError(
      "Malformed inline media data URL",
      "alta_multimodal_invalid_data",
    );
  const header = value.slice(5, comma).toLowerCase();
  if (!header.endsWith(";base64"))
    throw multimodalError(
      "Inline media must use base64 encoding",
      "alta_multimodal_invalid_data",
    );
  const mime = header.slice(0, -7);
  const payload = value.slice(comma + 1);
  if (payload.length % 4 === 1 || !/^[A-Za-z0-9+/]*={0,2}$/.test(payload))
    throw multimodalError(
      "Inline media contains invalid base64",
      "alta_multimodal_invalid_data",
    );
  const padding = payload.endsWith("==") ? 2 : payload.endsWith("=") ? 1 : 0;
  return {
    mime,
    payload,
    decodedBytes: Math.max(0, Math.floor((payload.length * 3) / 4) - padding),
    encodedBytes: payload.length,
  };
}

function base64Payload(value, mime) {
  if (typeof value !== "string" || !value) return null;
  const inline = dataUrl(value);
  if (inline) return inline;
  if (value.length % 4 === 1 || !/^[A-Za-z0-9+/]*={0,2}$/.test(value))
    throw multimodalError(
      "Inline media contains invalid base64",
      "alta_multimodal_invalid_data",
    );
  const padding = value.endsWith("==") ? 2 : value.endsWith("=") ? 1 : 0;
  return {
    mime,
    payload: value,
    decodedBytes: Math.max(0, Math.floor((value.length * 3) / 4) - padding),
    encodedBytes: value.length,
  };
}

function validateAudio(inline) {
  if (!inline || !["audio/wav", "audio/x-wav"].includes(inline.mime))
    throw multimodalError(
      "Audio input must be a base64 WAV data URL",
      "alta_multimodal_audio_type",
    );
  const wave = Buffer.from(inline.payload, "base64");
  const declaredBytes = wave.length >= 8 ? wave.readUInt32LE(4) + 8 : 0;
  if (
    wave.length < 44 ||
    wave.toString("ascii", 0, 4) !== "RIFF" ||
    wave.toString("ascii", 8, 12) !== "WAVE" ||
    declaredBytes !== wave.length
  )
    throw multimodalError(
      `Audio input must be a valid WAV no longer than ${MAX_AUDIO_SECONDS} seconds`,
      "alta_multimodal_audio_duration",
    );
  let format;
  let dataBytes;
  for (let offset = 12; offset + 8 <= wave.length; ) {
    const chunk = wave.toString("ascii", offset, offset + 4);
    const length = wave.readUInt32LE(offset + 4);
    const start = offset + 8;
    const end = start + length;
    if (end > wave.length)
      throw multimodalError(
        `Audio input must be a valid WAV no longer than ${MAX_AUDIO_SECONDS} seconds`,
        "alta_multimodal_audio_duration",
      );
    if (chunk === "fmt " && length >= 16) {
      const encoding = wave.readUInt16LE(start);
      const channels = wave.readUInt16LE(start + 2);
      const sampleRate = wave.readUInt32LE(start + 4);
      const byteRate = wave.readUInt32LE(start + 8);
      const blockAlign = wave.readUInt16LE(start + 12);
      const bitsPerSample = wave.readUInt16LE(start + 14);
      const bytesPerSample = Math.ceil(bitsPerSample / 8);
      const validEncoding =
        (encoding === 1 && [8, 16, 24, 32].includes(bitsPerSample)) ||
        (encoding === 3 && [32, 64].includes(bitsPerSample));
      if (
        !validEncoding ||
        channels < 1 ||
        channels > 8 ||
        sampleRate < 1 ||
        sampleRate > 384_000 ||
        blockAlign !== channels * bytesPerSample ||
        byteRate !== sampleRate * blockAlign
      )
        throw multimodalError(
          `Audio input must be a valid WAV no longer than ${MAX_AUDIO_SECONDS} seconds`,
          "alta_multimodal_audio_duration",
        );
      format = { byteRate };
    } else if (chunk === "data") dataBytes = length;
    offset = end + (length % 2);
  }
  const seconds =
    format && dataBytes !== undefined
      ? dataBytes / format.byteRate
      : Number.POSITIVE_INFINITY;
  if (!Number.isFinite(seconds) || seconds > MAX_AUDIO_SECONDS)
    throw multimodalError(
      `Audio input must be a valid WAV no longer than ${MAX_AUDIO_SECONDS} seconds`,
      "alta_multimodal_audio_duration",
    );
  return seconds;
}

function validatedReference(
  value,
  { allowMoonshot = false, allowHttps = true } = {},
) {
  if (typeof value !== "string" || !value || value.length > 4_096)
    throw multimodalError(
      "Media reference must contain 1-4096 characters",
      "alta_multimodal_invalid_reference",
    );
  if (allowMoonshot && /^ms:\/\/[A-Za-z0-9._:-]{1,200}$/.test(value)) return;
  if (!allowHttps)
    throw multimodalError(
      "Kimi media references must use an uploaded ms:// file ID",
      "alta_multimodal_invalid_reference",
    );
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw multimodalError(
      "Media references must use HTTPS",
      "alta_multimodal_invalid_reference",
    );
  }
  if (
    parsed.protocol !== "https:" ||
    parsed.username ||
    parsed.password ||
    parsed.port
  )
    throw multimodalError(
      "Media references must use credential-free HTTPS",
      "alta_multimodal_invalid_reference",
    );
}

function fileKind(item, inline) {
  const mime = inline?.mime ?? "";
  const filename = String(item.filename ?? item.file_url ?? "").toLowerCase();
  if (
    KIMI_IMAGE_MIMES.has(mime) ||
    /\.(?:bmp|gif|heic|heif|jpe?g|png|webp)$/.test(filename)
  )
    return "image";
  if (
    KIMI_VIDEO_MIMES.has(mime) ||
    /\.(?:3gp|avi|flv|mpe?g|mov|mp4|webm|wmv)$/.test(filename)
  )
    return "video";
  if (TEXT_FILE_MIMES.has(mime) || mime.startsWith("text/")) return "text";
  return "unsupported";
}

function allowedImageMimes(providerName) {
  if (providerName === "deepseek") return DEEPSEEK_IMAGE_MIMES;
  return providerName === "xai" ? XAI_IMAGE_MIMES : KIMI_IMAGE_MIMES;
}

function detectedImageMime(inline) {
  const header = Buffer.from(inline.payload.slice(0, 24), "base64");
  if (
    header.length >= 3 &&
    header[0] === 0xff &&
    header[1] === 0xd8 &&
    header[2] === 0xff
  )
    return "image/jpeg";
  if (
    header.length >= 8 &&
    header
      .subarray(0, 8)
      .equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))
  )
    return "image/png";
  const signature = header.toString("ascii");
  if (signature.startsWith("GIF87a") || signature.startsWith("GIF89a"))
    return "image/gif";
  if (
    header.length >= 12 &&
    signature.startsWith("RIFF") &&
    signature.slice(8, 12) === "WEBP"
  )
    return "image/webp";
  return null;
}

function isCurrentInputItem(item) {
  return (
    CURRENT_INPUT_TYPES.has(item?.type) &&
    !(item.type === "message" && item.role === "assistant")
  );
}

export function validateMultimodalRequest(
  body,
  providerName,
  capabilities,
  limits,
) {
  const supported = new Set(capabilities?.inputModalities ?? ["text"]);
  const profile = {
    imageItems: 0,
    audioItems: 0,
    fileItems: 0,
    inlineEncodedBytes: 0,
    inlineDecodedBytes: 0,
    hasMedia: false,
  };
  let currentDecodedBytes = 0;
  let currentMediaItems = 0;
  let currentMediaTokens = 0;
  const accountTokens = (tokens, current) => {
    if (!current) return;
    currentMediaTokens += tokens;
    if (currentMediaTokens > (limits.maxMediaTokens ?? MAX_MEDIA_TOKENS))
      throw multimodalError(
        "Current input exceeds the ALTA multimodal token-equivalent budget; split media across bounded agent handoffs",
        "alta_multimodal_token_limit",
      );
  };
  const accountInline = (inline, current) => {
    if (!inline) return;
    profile.inlineEncodedBytes += inline.encodedBytes;
    profile.inlineDecodedBytes += inline.decodedBytes;
    if (!current) return;
    currentDecodedBytes += inline.decodedBytes;
    if (
      inline.decodedBytes > limits.maxMultimodalBytes ||
      currentDecodedBytes > limits.maxMultimodalBytes
    )
      throw multimodalError(
        "Inline media exceeds the ALTA multimodal byte limit; use a shared workspace path or provider file ID",
        "alta_multimodal_too_large",
      );
  };
  const visit = (value, current, messageRole = null) => {
    if (!value || typeof value !== "object") return;
    const nestedRole = value.type === "message" ? value.role : messageRole;
    if (value.type === "input_image") {
      if (!supported.has("image"))
        throw multimodalError(
          `${body.model} does not support image input; delegate the shared media path to an image-capable ALTA agent`,
          "alta_multimodal_image_unsupported",
        );
      if (
        providerName === "deepseek" &&
        ["system", "assistant"].includes(messageRole)
      )
        throw multimodalError(
          "DeepSeek image input is allowed only in user/developer messages or tool outputs",
          "alta_multimodal_image_role",
        );
      const hasImageUrl = value.image_url !== undefined;
      const hasFileId = value.file_id !== undefined;
      if (hasImageUrl === hasFileId)
        throw multimodalError(
          "Image input requires exactly one image_url or file_id",
          "alta_multimodal_invalid_reference",
        );
      if (
        value.detail !== undefined &&
        !["low", "high", "original", "auto"].includes(value.detail)
      )
        throw multimodalError(
          "Image detail must be low, high, original, or auto",
          "alta_multimodal_invalid_reference",
        );
      const reference = hasImageUrl ? value.image_url : value.file_id;
      if (typeof reference !== "string" || !reference)
        throw multimodalError(
          "Image input requires a non-empty image_url or file_id",
          "alta_multimodal_invalid_reference",
        );
      const inline = dataUrl(reference);
      if (inline) {
        const mime =
          providerName === "deepseek" ? detectedImageMime(inline) : inline.mime;
        if (!mime || !allowedImageMimes(providerName).has(mime))
          throw multimodalError(
            `${providerName} does not support ${mime || "this image type"}`,
            "alta_multimodal_image_type",
          );
      }
      if (!inline) {
        if (hasFileId && providerName === "deepseek") {
          if (!/^file-api-[A-Za-z0-9._:-]{1,190}$/.test(value.file_id))
            throw multimodalError(
              "DeepSeek image file IDs must use the file-api-* format",
              "alta_multimodal_invalid_reference",
            );
        } else {
          const normalized = hasFileId ? `ms://${value.file_id}` : reference;
          validatedReference(normalized, {
            allowMoonshot: providerName === "kimi",
            allowHttps: providerName !== "kimi",
          });
        }
      }
      accountInline(inline, current);
      accountTokens(
        providerName === "deepseek"
          ? DEEPSEEK_IMAGE_TOKEN_COST
          : IMAGE_TOKEN_COST,
        current,
      );
      profile.imageItems += 1;
      currentMediaItems += current ? 1 : 0;
    } else if (value.type === "input_audio") {
      if (providerName === "kimi" || !supported.has("audio"))
        throw multimodalError(
          `${body.model} does not support audio input; transcribe with an audio-capable ALTA agent and hand off the transcript path`,
          "alta_multimodal_audio_unsupported",
        );
      const audioData =
        value.audio_url ?? value.input_audio?.data ?? value.data ?? null;
      const format = String(value.input_audio?.format ?? value.format ?? "wav")
        .toLowerCase()
        .replace(/[^a-z0-9.+-]/g, "");
      const inline = base64Payload(audioData, `audio/${format || "wav"}`);
      accountInline(inline, current);
      const seconds = validateAudio(inline);
      accountTokens(
        Math.max(1, Math.ceil(seconds * AUDIO_TOKENS_PER_SECOND)),
        current,
      );
      profile.audioItems += 1;
      currentMediaItems += current ? 1 : 0;
    } else if (value.type === "input_file") {
      if (!["kimi", "xai"].includes(providerName))
        throw multimodalError(
          `${providerName} does not accept portable file inputs on this route; use workspace tools or an OpenAI/Kimi agent`,
          "alta_multimodal_file_unsupported",
        );
      if (providerName === "xai") {
        if (value.file_url) validatedReference(value.file_url);
        else if (!/^[A-Za-z0-9._:-]{1,200}$/.test(value.file_id ?? ""))
          throw multimodalError(
            "xAI file input requires a credential-free HTTPS file_url or uploaded file_id",
            "alta_multimodal_invalid_reference",
          );
        if (value.file_data)
          throw multimodalError(
            "xAI inline files must be uploaded first and referenced by file_id",
            "alta_multimodal_file_type",
          );
        accountTokens(PROVIDER_FILE_TOKEN_COST, current);
        profile.fileItems += 1;
        currentMediaItems += current ? 1 : 0;
        return;
      }
      const inline = dataUrl(value.file_data);
      const kind = fileKind(value, inline);
      if (kind === "unsupported")
        throw multimodalError(
          "Kimi file input must be an inline text/image/video or a typed Moonshot file reference",
          "alta_multimodal_file_type",
        );
      if (["image", "video"].includes(kind) && !supported.has("image"))
        throw multimodalError(
          `${body.model} does not support visual file input`,
          "alta_multimodal_image_unsupported",
        );
      if (kind === "video" && capabilities?.video !== true)
        throw multimodalError(
          `${body.model} does not support video input`,
          "alta_multimodal_video_unsupported",
        );
      accountTokens(
        kind === "image"
          ? IMAGE_TOKEN_COST
          : kind === "video"
            ? VIDEO_TOKEN_COST
            : TEXT_PREVIEW_TOKEN_COST,
        current,
      );
      if (!inline) {
        const reference =
          value.file_url ?? (value.file_id ? `ms://${value.file_id}` : "");
        validatedReference(reference, {
          allowMoonshot: true,
          allowHttps: false,
        });
      }
      accountInline(inline, current);
      profile.fileItems += 1;
      currentMediaItems += current ? 1 : 0;
    }
    for (const nested of Object.values(value))
      visit(nested, current, nestedRole);
  };
  const input = Array.isArray(body.input) ? body.input : [];
  const lastInputIndex = input.findLastIndex(isCurrentInputItem);
  const lastBoundary = input.findLastIndex(
    (item, index) => index < lastInputIndex && !isCurrentInputItem(item),
  );
  const currentTurnId =
    input[lastInputIndex]?.internal_chat_message_metadata_passthrough?.turn_id;
  for (const [index, item] of input.entries()) {
    const itemTurnId =
      item?.internal_chat_message_metadata_passthrough?.turn_id;
    const current =
      index > lastBoundary || (currentTurnId && itemTurnId === currentTurnId);
    if (current) visit(item, true);
  }
  if (currentMediaItems > limits.maxMediaItems)
    throw multimodalError(
      `Current input contains ${currentMediaItems} media items; ALTA allows ${limits.maxMediaItems}`,
      "alta_multimodal_item_limit",
    );
  const imageGeneration = (body.tools ?? []).some(
    (tool) => tool?.type === "image_generation",
  );
  if (imageGeneration && providerName !== "xai")
    throw multimodalError(
      "This provider does not expose the Responses image-generation tool; use the portable image generation tool instead",
      "alta_multimodal_tool_unsupported",
    );
  profile.hasMedia =
    profile.imageItems + profile.audioItems + profile.fileItems > 0 ||
    imageGeneration;
  return profile;
}

function utf8Prefix(value, maximumBytes) {
  const bytes = Buffer.isBuffer(value)
    ? value
    : Buffer.from(String(value), "utf8");
  const prefix =
    bytes.length <= maximumBytes ? bytes : bytes.subarray(0, maximumBytes);
  return prefix.toString("utf8").replace(/\uFFFD+$/u, "");
}

function boundedTextPart(inline, filename, maximumBytes) {
  const naturallyTruncated = inline.decodedBytes > maximumBytes;
  const encodedLimit = Math.ceil((maximumBytes * 4) / 3) + 4;
  const source = Buffer.from(inline.payload.slice(0, encodedLimit), "base64");
  const label = utf8Prefix(filename || "attachment", 100).replace(
    /[\u0000-\u001f\u007f]/g,
    " ",
  );
  const suffix =
    "\n...[ALTA preview truncated; inspect the shared workspace file]";
  const build = (length, truncated) => ({
    type: "text",
    text: `[File: ${label}]\n${utf8Prefix(source.subarray(0, length), length)}${truncated ? suffix : ""}`,
  });
  const complete = build(source.length, naturallyTruncated);
  if (Buffer.byteLength(JSON.stringify(complete)) <= maximumBytes)
    return complete;
  let low = 0;
  let high = Math.min(source.length, maximumBytes);
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (Buffer.byteLength(JSON.stringify(build(middle, true))) <= maximumBytes)
      low = middle;
    else high = middle - 1;
  }
  return build(low, true);
}

export function kimiContentPart(item, maximumTextFileBytes = 900) {
  if (item?.type === "input_image") {
    const url = item.image_url ?? `ms://${item.file_id}`;
    return {
      type: "image_url",
      image_url: {
        url,
        ...(item.detail ? { detail: item.detail } : {}),
      },
    };
  }
  if (item?.type !== "input_file") return null;
  const inline = dataUrl(item.file_data);
  const kind = fileKind(item, inline);
  const url =
    item.file_data ??
    item.file_url ??
    (item.file_id ? `ms://${item.file_id}` : "");
  if (kind === "image") return { type: "image_url", image_url: { url } };
  if (kind === "video") return { type: "video_url", video_url: { url } };
  if (kind === "text" && inline)
    return boundedTextPart(inline, item.filename, maximumTextFileBytes);
  return null;
}
