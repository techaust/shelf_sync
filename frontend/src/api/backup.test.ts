// SET-05 (risk R8 in m2.0 section 4): the export's answer becomes a Blob with its name from Content-Disposition, saved
// through a same-page blob: link; the left-out header is read into codes and slots; the passphrase goes only in the
// POST body (never the address); a refusal is an ApiError like every other call. fetch is mocked: nothing leaves the
// test.
import { describe, expect, it, vi } from "vitest";
import {
  BACKUP_EXPORT_PATH,
  BACKUP_IMPORT_PATH,
  type DownloadHost,
  exportBackup,
  FALLBACK_FILE_NAME,
  fileNameFrom,
  importBackup,
  parseLeftOut,
  REVOKE_AFTER_MS,
  saveBlob,
} from "./backup";
import { ApiError, CSRF_HEADER, createApiClient } from "./client";

const PASSPHRASE = "sample passphrase for tests"; // made up
const FILE_TEXT = '{"format":"shelfsync-export","version":1,"encryption":null}';

function fileResponse(headers: Record<string, string>): Response {
  return new Response(FILE_TEXT, { status: 200, headers: { "Content-Type": "application/json", ...headers } });
}

describe("the file's name (Content-Disposition)", () => {
  it("takes the server's .ssbak name", () => {
    expect(fileNameFrom('attachment; filename="shelfsync-export-2026-10-29.ssbak"')).toBe(
      "shelfsync-export-2026-10-29.ssbak",
    );
  });

  it.each([
    null,
    "attachment",
    'attachment; filename="../../evil.ssbak"',
    'attachment; filename="C:\\Users\\x.ssbak"',
    'attachment; filename="shelfsync.exe"',
    'attachment; filename=".ssbak"',
    'attachment; filename="name with spaces.ssbak"',
  ])("falls back to 13's example name for %s", (header) => {
    expect(fileNameFrom(header)).toBe(FALLBACK_FILE_NAME);
  });
});

describe("X-ShelfSync-Left-Out", () => {
  it("absent: nothing left out", () => expect(parseLeftOut(null)).toBeNull());

  it("store codes, slots and the token", () => {
    expect(parseLeftOut("stores:GF,PW;s3:rw,ro;github")).toEqual({
      stores: ["GF", "PW"],
      s3: ["rw", "ro"],
      github: true,
    });
    expect(parseLeftOut("s3:ro")).toEqual({ stores: [], s3: ["ro"], github: false });
  });

  it("anything else in it is skipped, never echoed", () => {
    expect(parseLeftOut("stores:gf,<b>,PWX;s3:admin;secret:xyz")).toEqual({ stores: [], s3: [], github: false });
  });
});

describe("export through the API client", () => {
  it("POSTs the passphrase in the body only, and gives back the Blob, its name and the left-out codes", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () =>
      fileResponse({
        "Content-Disposition": 'attachment; filename="shelfsync-export-2026-10-29.ssbak"',
        "X-ShelfSync-Left-Out": "stores:GF",
      }),
    );
    const file = await exportBackup(createApiClient({ fetch: fetchMock }), PASSPHRASE);
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe(BACKUP_EXPORT_PATH);
    expect(String(url)).not.toContain("sample");
    expect(init?.method).toBe("POST");
    expect((init?.headers as Record<string, string> | undefined)?.[CSRF_HEADER]).toBe("1");
    expect(JSON.parse(String(init?.body))).toEqual({ passphrase: PASSPHRASE });
    expect(file.fileName).toBe("shelfsync-export-2026-10-29.ssbak");
    expect(file.leftOut).toEqual({ stores: ["GF"], s3: [], github: false });
    expect(file.blob).toBeInstanceOf(Blob);
    expect(file.blob.type).toBe("application/json");
    expect(await file.blob.text()).toBe(FILE_TEXT);
  });

  it("without secrets sends null; no header means nothing left out", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () =>
      fileResponse({ "Content-Disposition": 'attachment; filename="shelfsync-export-2026-10-29.ssbak"' }),
    );
    const file = await exportBackup(createApiClient({ fetch: fetchMock }), null);
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ passphrase: null });
    expect(file.leftOut).toBeNull();
  });

  it("a refusal is an ApiError with its code, and no Blob is made", async () => {
    const fetchMock = vi.fn<typeof fetch>(
      async () =>
        new Response(JSON.stringify({ error: "busy" }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
    );
    await expect(exportBackup(createApiClient({ fetch: fetchMock }), null)).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      code: "busy",
    });
    await expect(exportBackup(createApiClient({ fetch: fetchMock }), null)).rejects.toBeInstanceOf(ApiError);
  });
});

describe("saving the Blob (the browser's own download)", () => {
  it("a blob: address for the Blob, a click on a link named after the file, then the address is let go", () => {
    const later: (() => void)[] = [];
    const host: DownloadHost = {
      createObjectURL: vi.fn(() => "blob:http://127.0.0.1:47615/0000"),
      revokeObjectURL: vi.fn(),
      clickLink: vi.fn(),
      later: vi.fn((run: () => void, ms: number) => {
        expect(ms).toBe(REVOKE_AFTER_MS);
        later.push(run);
      }),
    };
    const blob = new Blob([FILE_TEXT], { type: "application/json" });
    saveBlob({ blob, fileName: "shelfsync-export-2026-10-29.ssbak" }, host);
    expect(host.createObjectURL).toHaveBeenCalledWith(blob);
    expect(host.clickLink).toHaveBeenCalledWith(
      "blob:http://127.0.0.1:47615/0000",
      "shelfsync-export-2026-10-29.ssbak",
    );
    expect(host.revokeObjectURL).not.toHaveBeenCalled();
    for (const run of later) run();
    expect(host.revokeObjectURL).toHaveBeenCalledWith("blob:http://127.0.0.1:47615/0000");
  });

  it("the address is let go even if the click throws", () => {
    const host: DownloadHost = {
      createObjectURL: () => "blob:x",
      revokeObjectURL: vi.fn(),
      clickLink: () => {
        throw new Error("no download here");
      },
      later: (run) => run(),
    };
    expect(() => saveBlob({ blob: new Blob(["x"]), fileName: "a.ssbak" }, host)).toThrow();
    expect(host.revokeObjectURL).toHaveBeenCalledWith("blob:x");
  });
});

describe("import through the API client", () => {
  it("POSTs the file's text and the passphrase as JSON (no multipart), and reads the counts", async () => {
    const fetchMock = vi.fn<typeof fetch>(
      async () =>
        new Response(JSON.stringify({ stores: 2, settings: 12, secrets: 9, encrypted: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    const result = await importBackup(createApiClient({ fetch: fetchMock }), FILE_TEXT, PASSPHRASE);
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe(BACKUP_IMPORT_PATH);
    expect(JSON.parse(String(init?.body))).toEqual({ file: FILE_TEXT, passphrase: PASSPHRASE });
    expect(result).toEqual({ stores: 2, settings: 12, secrets: 9, encrypted: true });
  });
});
