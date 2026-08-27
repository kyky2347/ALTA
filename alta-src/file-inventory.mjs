import fs from "node:fs";
import path from "node:path";

async function mapConcurrent(values, concurrency, operation) {
  if (!values.length) return [];
  const results = new Array(values.length);
  let next = 0;
  const workers = Array.from(
    { length: Math.min(concurrency, values.length) },
    async () => {
      while (next < values.length) {
        const index = next;
        next += 1;
        results[index] = await operation(values[index]);
      }
    },
  );
  await Promise.all(workers);
  return results;
}

export async function walkFiles(root, concurrency = 16) {
  const files = [];
  const directories = [root];
  let nextDirectory = 0;
  while (nextDirectory < directories.length) {
    const batch = directories.slice(nextDirectory, nextDirectory + concurrency);
    nextDirectory += batch.length;
    const listings = await Promise.all(
      batch.map(async (directory) => {
        try {
          return {
            directory,
            entries: await fs.promises.readdir(directory, {
              withFileTypes: true,
            }),
          };
        } catch (error) {
          if (error.code === "ENOENT") return { directory, entries: [] };
          throw error;
        }
      }),
    );
    const pendingFiles = [];
    for (const { directory, entries } of listings) {
      for (const entry of entries) {
        const file = path.join(directory, entry.name);
        if (entry.isDirectory()) directories.push(file);
        else if (entry.isFile()) pendingFiles.push(file);
      }
    }
    const stats = await mapConcurrent(
      pendingFiles,
      concurrency,
      async (file) => {
        try {
          const stat = await fs.promises.stat(file);
          return { file, size: stat.size, mtimeMs: stat.mtimeMs };
        } catch (error) {
          if (error.code === "ENOENT") return null;
          throw error;
        }
      },
    );
    files.push(...stats.filter(Boolean));
  }
  return files;
}

export async function unlinkFiles(files, concurrency = 16) {
  const outcomes = await mapConcurrent(files, concurrency, async (file) => {
    try {
      await fs.promises.unlink(file);
      return { file, removed: true };
    } catch (error) {
      if (error.code === "ENOENT") return { file, removed: true };
      return {
        file,
        removed: false,
        error: String(error.message ?? error).slice(0, 1_000),
      };
    }
  });
  return {
    removed: outcomes.filter((item) => item.removed).map((item) => item.file),
    failures: outcomes
      .filter((item) => !item.removed)
      .map(({ file, error }) => ({ file, error })),
  };
}
