import { Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

export interface DroppedFile {
  name: string;
  type: string;
  content: Buffer;
}

export function fromDisk(filePath: string, type: string): DroppedFile {
  return { name: path.basename(filePath), type, content: fs.readFileSync(filePath) };
}

/**
 * Dispatches a `drop` carrying `files` on the element matching `selector`.
 * The DataTransfer is built inside the page, because one cannot be passed in
 * from the test process. A DataTransfer built in script returns null from
 * webkitGetAsEntry(), which the app treats as "this is a file".
 *
 * This exercises the app's own handlers. It cannot show what the browser does
 * with a file that misses the zone: a synthetic event never triggers the
 * browser's default navigation.
 */
export async function dropFiles(page: Page, selector: string, files: DroppedFile[]): Promise<void> {
  const payload = files.map((f) => ({
    name: f.name,
    type: f.type,
    base64: f.content.toString('base64'),
  }));
  const dataTransfer = await page.evaluateHandle((items) => {
    const transfer = new DataTransfer();
    for (const item of items) {
      const bytes = Uint8Array.from(atob(item.base64), (c) => c.charCodeAt(0));
      // A fixed lastModified: the app recognises a duplicate by name, size and
      // lastModified, and the default (the current time) would differ per drop.
      transfer.items.add(new File([bytes], item.name, { type: item.type, lastModified: 1 }));
    }
    return transfer;
  }, payload);
  await page.dispatchEvent(selector, 'drop', { dataTransfer });
}
