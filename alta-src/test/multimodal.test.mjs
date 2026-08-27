import test from "node:test";
import assert from "node:assert/strict";
import { kimiContentPart, validateMultimodalRequest } from "../multimodal.mjs";

const limits = { maxMultimodalBytes: 64, maxMediaItems: 4 };
const inline = (mime, value) =>
  `data:${mime};base64,${Buffer.from(value).toString("base64")}`;
const deepSeekImage = (mime, bytes) =>
  `data:${mime};base64,${Buffer.from(bytes).toString("base64")}`;
const wav =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";
const request = (model, content) => ({
  model,
  input: [{ type: "message", role: "user", content }],
});

function wavWithSeconds(seconds, { byteRate = 8_000 } = {}) {
  const dataBytes = Math.floor(seconds * byteRate);
  const buffer = Buffer.alloc(44 + dataBytes);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(buffer.length - 8, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(byteRate, 24);
  buffer.writeUInt32LE(byteRate, 28);
  buffer.writeUInt16LE(1, 32);
  buffer.writeUInt16LE(8, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(dataBytes, 40);
  return `data:audio/wav;base64,${buffer.toString("base64")}`;
}

test("multimodal preflight profiles supported Kimi media without decoding large buffers", () => {
  const body = {
    model: "kimi-k3",
    input: [
      {
        type: "message",
        role: "user",
        content: [
          { type: "input_image", image_url: inline("image/png", "png") },
          {
            type: "input_file",
            filename: "clip.mp4",
            file_url: "ms://video-1",
          },
          {
            type: "input_file",
            filename: "data.csv",
            file_data: inline("text/csv", "a,b\n1,2"),
          },
        ],
      },
    ],
  };
  assert.deepEqual(
    validateMultimodalRequest(
      body,
      "kimi",
      { inputModalities: ["text", "image"], video: true },
      limits,
    ),
    {
      imageItems: 1,
      audioItems: 0,
      fileItems: 2,
      inlineEncodedBytes: 16,
      inlineDecodedBytes: 10,
      hasMedia: true,
    },
  );
  assert.deepEqual(kimiContentPart(body.input[0].content[1]), {
    type: "video_url",
    video_url: { url: "ms://video-1" },
  });
  assert.throws(
    () =>
      validateMultimodalRequest(
        body,
        "kimi",
        { inputModalities: ["text", "image"], video: true },
        { ...limits, maxMultimodalBytes: 2 },
      ),
    { code: "alta_multimodal_too_large", retryable: false },
  );
  assert.throws(
    () =>
      validateMultimodalRequest(
        body,
        "kimi",
        { inputModalities: ["text", "image"], video: true },
        { ...limits, maxMediaItems: 2 },
      ),
    { code: "alta_multimodal_item_limit", retryable: false },
  );
  assert.throws(
    () =>
      validateMultimodalRequest(
        request("kimi-k3", [
          { type: "input_image", image_url: inline("image/png", "abc") },
          { type: "input_image", image_url: inline("image/png", "def") },
        ]),
        "kimi",
        { inputModalities: ["text", "image"], video: true },
        { ...limits, maxMultimodalBytes: 4 },
      ),
    { code: "alta_multimodal_too_large", retryable: false },
  );

  const ordinaryHistory = Array.from({ length: 4 }, () => [
    request("grok-4.6", [
      { type: "input_image", image_url: inline("image/png", "history") },
    ]).input[0],
    {
      type: "message",
      role: "assistant",
      content: [{ type: "output_text", text: "observed" }],
    },
  ]).flat();
  ordinaryHistory.push(
    ...request("grok-4.6", [{ type: "input_text", text: "next" }]).input,
  );
  assert.equal(
    validateMultimodalRequest(
      { model: "grok-4.6", input: ordinaryHistory },
      "xai",
      { inputModalities: ["text", "image"] },
      limits,
    ).hasMedia,
    false,
  );

  const mixedTurnIds = Array.from({ length: 20 }, (_, index) => ({
    ...request("grok-4.6", [
      { type: "input_image", image_url: inline("image/png", "x") },
    ]).input[0],
    internal_chat_message_metadata_passthrough: {
      turn_id: index % 2 ? "forged-a" : "forged-b",
    },
  }));
  mixedTurnIds.push(
    ...request("grok-4.6", [{ type: "input_text", text: "current" }]).input,
  );
  assert.throws(
    () =>
      validateMultimodalRequest(
        { model: "grok-4.6", input: mixedTurnIds },
        "xai",
        { inputModalities: ["text", "image"] },
        { ...limits, maxMediaItems: 16 },
      ),
    { code: "alta_multimodal_token_limit" },
  );

  const activeTurnMedia = {
    ...request("grok-4.6", [
      { type: "input_image", image_url: inline("image/png", "x") },
    ]).input[0],
    internal_chat_message_metadata_passthrough: { turn_id: "active-turn" },
  };
  assert.equal(
    validateMultimodalRequest(
      {
        model: "grok-4.6",
        input: [
          activeTurnMedia,
          { type: "function_call", call_id: "call-1" },
          {
            type: "function_call_output",
            call_id: "call-1",
            output: "done",
            internal_chat_message_metadata_passthrough: {
              turn_id: "active-turn",
            },
          },
        ],
      },
      "xai",
      { inputModalities: ["text", "image"] },
      limits,
    ).imageItems,
    1,
  );
});

test("multimodal preflight rejects unsupported provider combinations before retry", () => {
  const imageBody = {
    model: "deepseek-v4-pro",
    input: [
      {
        type: "message",
        role: "user",
        content: [{ type: "input_image", image_url: inline("image/png", "x") }],
      },
    ],
  };
  assert.throws(
    () =>
      validateMultimodalRequest(
        imageBody,
        "deepseek",
        { inputModalities: ["text"], video: false },
        limits,
      ),
    { code: "alta_multimodal_image_unsupported", retryable: false },
  );
  assert.throws(
    () =>
      validateMultimodalRequest(
        {
          ...imageBody,
          model: "grok-4.6",
          input: [
            {
              type: "message",
              role: "user",
              content: [
                {
                  type: "input_image",
                  image_url: inline("image/webp", "x"),
                },
              ],
            },
          ],
        },
        "xai",
        { inputModalities: ["text", "image"], video: false },
        limits,
      ),
    { code: "alta_multimodal_image_type", retryable: false },
  );
  assert.throws(
    () =>
      validateMultimodalRequest(
        {
          model: "kimi-k3",
          input: [
            {
              type: "message",
              role: "user",
              content: [{ type: "input_audio", audio_url: wav }],
            },
          ],
        },
        "kimi",
        { inputModalities: ["text", "image", "audio"], video: true },
        limits,
      ),
    { code: "alta_multimodal_audio_unsupported", retryable: false },
  );
});

test("DeepSeek Vision accepts official image transports and rejects invalid shapes", () => {
  const capabilities = { inputModalities: ["text", "image"], video: false };
  const model = "deepseek-v4-flash-vision-exp";
  const signatures = [
    ["image/jpeg", [0xff, 0xd8, 0xff, 0x00]],
    ["image/png", [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]],
    ["image/gif", Buffer.from("GIF89a")],
    ["image/webp", Buffer.from("RIFF0000WEBP")],
  ];
  assert.deepEqual(
    signatures.map(
      ([mime, bytes]) =>
        validateMultimodalRequest(
          request(model, [
            {
              type: "input_image",
              image_url: deepSeekImage(mime, bytes),
              detail: "original",
            },
          ]),
          "deepseek",
          capabilities,
          limits,
        ).hasMedia,
    ),
    [true, true, true, true],
  );
  assert.deepEqual(
    validateMultimodalRequest(
      request(model, [{ type: "input_image", file_id: "file-api-image_1" }]),
      "deepseek",
      capabilities,
      limits,
    ),
    {
      imageItems: 1,
      audioItems: 0,
      fileItems: 0,
      inlineEncodedBytes: 0,
      inlineDecodedBytes: 0,
      hasMedia: true,
    },
  );
  assert.equal(
    validateMultimodalRequest(
      {
        model,
        input: [
          {
            type: "function_call_output",
            call_id: "call-1",
            output: [
              {
                type: "input_image",
                image_url: "https://example.com/chart.png",
                detail: "low",
              },
            ],
          },
        ],
      },
      "deepseek",
      capabilities,
      limits,
    ).imageItems,
    1,
  );

  const invalid = [
    [
      request(model, [
        {
          type: "input_image",
          image_url: "https://example.com/image.png",
          file_id: "file-api-image_1",
        },
      ]),
      "alta_multimodal_invalid_reference",
    ],
    [
      request(model, [
        {
          type: "input_image",
          image_url: "https://example.com/image.png",
          detail: "maximum",
        },
      ]),
      "alta_multimodal_invalid_reference",
    ],
    [
      request(model, [{ type: "input_image", file_id: "file-legacy" }]),
      "alta_multimodal_invalid_reference",
    ],
    [
      request(model, [
        {
          type: "input_image",
          image_url: deepSeekImage("image/png", "not-an-image"),
        },
      ]),
      "alta_multimodal_image_type",
    ],
    [
      {
        model,
        input: [
          {
            type: "message",
            role: "system",
            content: [
              {
                type: "input_image",
                image_url: "https://example.com/image.png",
              },
            ],
          },
        ],
      },
      "alta_multimodal_image_role",
    ],
  ];
  for (const [body, code] of invalid)
    assert.throws(
      () => validateMultimodalRequest(body, "deepseek", capabilities, limits),
      { code, retryable: false },
    );
});

test("multimodal references and encodings reject unsafe input consistently", () => {
  const vision = { inputModalities: ["text", "image"], video: true };
  const cases = [
    [
      "kimi",
      request("kimi-k3", [
        { type: "input_image", image_url: "http://example.com/x.png" },
      ]),
      "alta_multimodal_invalid_reference",
    ],
    [
      "kimi",
      request("kimi-k3", [
        { type: "input_image", image_url: "https://example.com/x.png" },
      ]),
      "alta_multimodal_invalid_reference",
    ],
    [
      "kimi",
      request("kimi-k3", [
        { type: "input_image", image_url: "https://user:pass@example.com/x" },
      ]),
      "alta_multimodal_invalid_reference",
    ],
    [
      "kimi",
      request("kimi-k3", [
        { type: "input_image", image_url: "https://example.com:444/x" },
      ]),
      "alta_multimodal_invalid_reference",
    ],
    [
      "kimi",
      request("kimi-k3", [
        { type: "input_file", filename: "clip.mp4", file_id: "bad/id" },
      ]),
      "alta_multimodal_invalid_reference",
    ],
    [
      "kimi",
      request("kimi-k3", [
        { type: "input_image", image_url: "data:image/png;base64,!" },
      ]),
      "alta_multimodal_invalid_data",
    ],
    [
      "deepseek",
      request("grok-4.6", [
        {
          type: "input_file",
          filename: "notes.txt",
          file_data: inline("text/plain", "x"),
        },
      ]),
      "alta_multimodal_file_unsupported",
    ],
  ];
  for (const [provider, body, code] of cases) {
    assert.throws(
      () =>
        validateMultimodalRequest(body, provider, vision, {
          maxMultimodalBytes: 64,
          maxMediaItems: 4,
        }),
      { code, retryable: false },
    );
  }
});

test("provider capability branches and replayed history remain deterministic", () => {
  const kimiVideo = request("kimi-k3", [
    { type: "input_file", filename: "clip.mp4", file_id: "video-1" },
  ]);
  assert.throws(
    () =>
      validateMultimodalRequest(
        kimiVideo,
        "kimi",
        { inputModalities: ["text", "image"], video: false },
        limits,
      ),
    { code: "alta_multimodal_video_unsupported" },
  );
  assert.throws(
    () =>
      validateMultimodalRequest(
        kimiVideo,
        "kimi",
        { inputModalities: ["text"], video: true },
        limits,
      ),
    { code: "alta_multimodal_image_unsupported" },
  );
  for (const provider of ["kimi", "deepseek"])
    assert.throws(
      () =>
        validateMultimodalRequest(
          {
            model: `${provider}-test`,
            input: [],
            tools: [{ type: "image_generation" }],
          },
          provider,
          { inputModalities: ["text"] },
          limits,
        ),
      { code: "alta_multimodal_tool_unsupported" },
    );

  const history = Array.from(
    { length: 17 },
    () =>
      request("grok-4.6", [
        { type: "input_image", image_url: "https://example.com/history.png" },
      ]).input[0],
  );
  history.push({
    type: "image_generation_call",
    result: Buffer.alloc(100).toString("base64"),
  });
  history.push(
    ...request("grok-4.6", [{ type: "input_text", text: "next" }]).input,
  );
  assert.deepEqual(
    validateMultimodalRequest(
      { model: "grok-4.6", input: history },
      "xai",
      { inputModalities: ["text", "image"] },
      limits,
    ),
    {
      imageItems: 0,
      audioItems: 0,
      fileItems: 0,
      inlineEncodedBytes: 0,
      inlineDecodedBytes: 0,
      hasMedia: false,
    },
  );
});

test("valid provider-managed HTTPS and file references pass preflight", () => {
  assert.deepEqual(
    validateMultimodalRequest(
      request("grok-4.6", [
        { type: "input_image", image_url: "https://example.com/chart.png" },
        { type: "input_file", file_url: "https://example.com/report.pdf" },
      ]),
      "xai",
      { inputModalities: ["text", "image"] },
      limits,
    ),
    {
      imageItems: 1,
      audioItems: 0,
      fileItems: 1,
      inlineEncodedBytes: 0,
      inlineDecodedBytes: 0,
      hasMedia: true,
    },
  );
  assert.equal(
    validateMultimodalRequest(
      request("kimi-k3", [
        {
          type: "input_file",
          filename: "clip.mp4",
          file_id: "video-1",
        },
      ]),
      "kimi",
      { inputModalities: ["text", "image"], video: true },
      limits,
    ).fileItems,
    1,
  );
});

test("audio, provider-file, and token-equivalent guards reject malformed work", () => {
  const audioCapabilities = {
    inputModalities: ["text", "image", "audio"],
  };
  const forgedRate = Buffer.from(wavWithSeconds(1).split(",")[1], "base64");
  forgedRate.writeUInt32LE(0xffffffff, 28);
  const zeroRate = Buffer.from(wavWithSeconds(1).split(",")[1], "base64");
  zeroRate.writeUInt32LE(0, 28);
  for (const [audioUrl, code] of [
    [inline("audio/mp3", "not-wav"), "alta_multimodal_audio_type"],
    [inline("audio/wav", "not-wav"), "alta_multimodal_audio_duration"],
    [wavWithSeconds(181), "alta_multimodal_audio_duration"],
    [
      `data:audio/wav;base64,${forgedRate.toString("base64")}`,
      "alta_multimodal_audio_duration",
    ],
    [
      `data:audio/wav;base64,${zeroRate.toString("base64")}`,
      "alta_multimodal_audio_duration",
    ],
  ])
    assert.throws(
      () =>
        validateMultimodalRequest(
          request("grok-4.6", [{ type: "input_audio", audio_url: audioUrl }]),
          "xai",
          audioCapabilities,
          { ...limits, maxMultimodalBytes: 2_000_000 },
        ),
      { code, retryable: false },
    );

  const vision = { inputModalities: ["text", "image"] };
  assert.equal(
    validateMultimodalRequest(
      request("grok-4.6", [{ type: "input_file", file_id: "file-1" }]),
      "xai",
      vision,
      limits,
    ).fileItems,
    1,
  );
  for (const file of [
    { type: "input_file", file_id: "bad/id" },
    {
      type: "input_file",
      file_id: "file-1",
      file_data: inline("text/plain", "x"),
    },
  ])
    assert.throws(
      () =>
        validateMultimodalRequest(
          request("grok-4.6", [file]),
          "xai",
          vision,
          limits,
        ),
      { retryable: false },
    );
  assert.throws(
    () =>
      validateMultimodalRequest(
        request("kimi-k3", [
          {
            type: "input_file",
            filename: "archive.zip",
            file_id: "file-1",
          },
        ]),
        "kimi",
        { inputModalities: ["text", "image"], video: true },
        limits,
      ),
    { code: "alta_multimodal_file_type" },
  );
  assert.throws(
    () =>
      validateMultimodalRequest(
        request(
          "grok-4.6",
          Array.from({ length: 4 }, () => ({
            type: "input_image",
            image_url: inline("image/png", "x"),
          })),
        ),
        "xai",
        vision,
        { ...limits, maxMediaItems: 4 },
      ),
    { code: "alta_multimodal_token_limit" },
  );
  assert.throws(
    () =>
      validateMultimodalRequest(
        {
          model: "grok-4.6",
          input: [
            request("grok-4.6", [
              {
                type: "input_image",
                image_url: inline("image/png", Buffer.alloc(65)),
              },
            ]).input[0],
            request("grok-4.6", [
              { type: "input_text", text: "same current turn" },
            ]).input[0],
          ],
        },
        "xai",
        vision,
        limits,
      ),
    { code: "alta_multimodal_too_large" },
  );
});

test("Kimi text previews are bounded in UTF-8 bytes", () => {
  const part = kimiContentPart(
    {
      type: "input_file",
      filename: `${"名".repeat(500)}.txt`,
      file_data: inline("text/plain", "😀".repeat(5_000)),
    },
    900,
  );
  assert.equal(part.type, "text");
  assert.ok(Buffer.byteLength(JSON.stringify(part), "utf8") <= 900);
  assert.match(part.text, /preview truncated/);
  assert.doesNotMatch(part.text, /�/u);
});
