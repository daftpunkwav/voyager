/**
 * @file chat.spec
 * @description Realistic user flows on the chat page: composer guard states,
 * sending a message, and the streaming round trip (any agent-side bubble counts
 * — the LLM provider may legitimately fail in this environment).
 */

import { expect, test } from '@playwright/test';

const PING = `e2e ping ${Date.now()}`;

test.describe('chat page', () => {
  test('empty draft keeps send disabled', async ({ page }) => {
    await page.goto('/chat');
    const send = page.getByRole('button', { name: '发送' });
    await expect(send).toBeDisabled();
  });

  test('Shift+Enter inserts a newline without sending', async ({ page }) => {
    await page.goto('/chat');
    const box = page.getByRole('textbox', { name: /说点什么/ });
    await box.click();
    await box.pressSequentially('第一行');
    await box.press('Shift+Enter');
    await box.pressSequentially('第二行');
    await expect(box).toHaveValue('第一行\n第二行');
    // nothing was sent: no user bubble with our unique text (scope to message
    // paragraphs — getByText would also match the textarea's own value)
    await expect(page.locator('main p').filter({ hasText: '第一行' })).toHaveCount(0);
  });

  test('sending a message appends the user bubble and clears the draft', async ({ page }) => {
    test.setTimeout(90_000); // the agent turn (ReAct rounds + LLM) may take a while
    await page.goto('/chat');
    const box = page.getByRole('textbox', { name: /说点什么/ });
    await box.click();
    await box.pressSequentially(PING);
    await page.getByRole('button', { name: '发送' }).click();

    // optimistic user bubble appears and the draft is cleared
    await expect(page.getByText(PING).first()).toBeVisible({ timeout: 10_000 });
    await expect(box).toHaveValue('');

    // the streaming round trip must surface any agent-side event (reply,
    // provider-failure bubble, ...) — silence for a full minute is a bug
    const paragraphs = page.locator('main p');
    const after = await paragraphs.count();
    await expect
      .poll(async () => paragraphs.count(), { timeout: 60_000, intervals: [2_000, 5_000, 10_000] })
      .toBeGreaterThan(after);
  });

  test('Enter in the composer sends the message', async ({ page }) => {
    const text = `e2e enter ${Date.now()}`;
    await page.goto('/chat');
    const box = page.getByRole('textbox', { name: /说点什么/ });
    await box.click();
    await box.pressSequentially(text);
    await box.press('Enter');
    await expect(page.getByText(text).first()).toBeVisible({ timeout: 10_000 });
    await expect(box).toHaveValue('');
  });

  test('history anchors to the newest message on load (no scroll-from-top journey)', async ({
    page,
  }) => {
    await page.goto('/chat');
    await expect(page.locator('.chat-bubble').first()).toBeVisible({ timeout: 10_000 });
    // the stream must be pinned to its bottom edge: the pre-paint anchor
    // positions the viewport before the first frame instead of scrolling
    // through the whole history after it. Polled because sibling workers keep
    // sending messages, whose tail-scroll animations may be mid-flight right
    // after load; once traffic settles the stream rests pinned at the bottom.
    await expect
      .poll(
        async () =>
          page.evaluate(() => {
            const el = document.querySelector('.chat-stream');
            if (!el) return false;
            return Math.abs(el.scrollHeight - el.scrollTop - el.clientHeight) < 60;
          }),
        { timeout: 20_000, intervals: [200, 500, 1_000] }
      )
      .toBe(true);
  });
});
