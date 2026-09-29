import { Page } from '@playwright/test';

export const LOADING_NOTICE =
  'This may take a few minutes. Please be patient and do not reload the page.';

/**
 * Records whether the loading notice was shown in the Continue row. Call before
 * clicking Continue. A small test archive is processed faster than an assertion
 * can poll, so the page records the notice itself: the observer fires on the
 * render that follows the click, before the worker answers.
 *
 * "In the Continue row" means: the notice's parent is a flex row with exactly
 * two children, the Continue button first and the notice second, and the
 * notice takes up space on screen. A notice below the prompt does not count:
 * its parent is the whole panel, which has more children than two.
 */
export async function watchForNotice(page: Page): Promise<void> {
  await page.evaluate((notice) => {
    const state = window as unknown as { __noticeBesideContinue?: boolean };
    state.__noticeBesideContinue = false;
    new MutationObserver(() => {
      for (const el of Array.from(document.querySelectorAll<HTMLElement>('div'))) {
        if (el.textContent?.trim() !== notice) continue;
        const row = el.parentElement;
        if (row === null) continue;
        const inRow =
          row.classList.contains('flex-row') &&
          row.children.length === 2 &&
          row.children[0].getAttribute('role') === 'button' &&
          row.children[0].textContent?.includes('Continue') === true &&
          row.children[1] === el;
        const shown = el.getClientRects().length > 0 &&
          getComputedStyle(el).visibility !== 'hidden';
        if (inRow && shown) state.__noticeBesideContinue = true;
      }
    }).observe(document.body, { childList: true, subtree: true, characterData: true });
  }, LOADING_NOTICE);
}

export async function noticeWasBesideContinue(page: Page): Promise<boolean> {
  return await page.evaluate(
    () => (window as unknown as { __noticeBesideContinue?: boolean }).__noticeBesideContinue === true
  );
}
