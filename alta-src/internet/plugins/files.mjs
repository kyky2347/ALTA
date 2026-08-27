import { defineTool } from "./support.mjs";

export const filesPlugin = {
  id: "alta-local-file-reading",
  tools: [
    defineTool(
      "alta_file_read",
      "ALTA File Read",
      "Read a workspace file as bounded, paginated text. Supports text/code/data, PDF, DOCX/XLSX/PPTX, OpenDocument, EPUB, ZIP/GZIP, RTF, and heuristic legacy binaries without exposing internal or credential paths.",
      {
        type: "object",
        properties: {
          path: {
            type: "string",
            description: "Absolute or workspace-relative file path.",
          },
          section: {
            type: "string",
            description: "Exact ZIP entry name returned in sections.",
          },
          cursor: {
            type: "integer",
            minimum: 0,
            description: "Character cursor from the prior next_cursor.",
          },
          page_chars: { type: "integer", minimum: 128, maximum: 700 },
        },
        required: ["path"],
        additionalProperties: false,
      },
      (service, args, options) => service.readLocalFile(args, options),
    ),
  ],
};
