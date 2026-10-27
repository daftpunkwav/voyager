/**
 * @file deliveryCard
 * @description Characterization tests for the delivery card: the head shows
 * the member, the status, the title and the elapsed time, the answer is
 * rendered as Markdown and folds behind the expander, a failed delivery
 * carries its error and the run pointer, and the copy button hands the
 * delivery text to the clipboard.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { DeliveryCard } from '@/widgets/chat/DeliveryCard';
import { initI18n } from '@/i18n';
import type { Delivery } from '@/stores/chatStore';

const writeText = vi.fn().mockResolvedValue(undefined);

function delivery(over: Partial<Delivery> = {}): Delivery {
  return {
    seq: 1,
    member: 'explainer',
    name: 'explainer-run',
    title: '讲 real-mock',
    status: 'done',
    content: '# RealMock\n\nAI 模拟面试平台,上传简历获得解析与深度评审。',
    elapsed_s: 42,
    run_id: 'run-77',
    ...over,
  };
}

beforeAll(() => {
  initI18n();
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
  });
});

beforeEach(() => {
  writeText.mockClear();
});

describe('DeliveryCard', () => {
  it('shows the member, the status, the title and the elapsed time', () => {
    render(<DeliveryCard delivery={delivery()} />);
    expect(screen.getByText('Elio')).toBeTruthy();
    expect(screen.getByText('完成')).toBeTruthy();
    expect(screen.getByText('讲 real-mock')).toBeTruthy();
    expect(screen.getByText('耗时 42 秒')).toBeTruthy();
  });

  it('renders the answer as Markdown, not as raw markup', () => {
    render(<DeliveryCard delivery={delivery()} />);
    expect(screen.getByText(/AI 模拟面试平台/)).toBeTruthy();
    expect(screen.queryByText(/\*\*用 markdown\*\*/)).toBeNull();
  });

  it('folds a long answer behind the expander and unfolds it on click', () => {
    const long = '很长的讲解。'.repeat(400);
    render(<DeliveryCard delivery={delivery({ content: long })} />);
    expect(screen.getByText(/很长的讲解。/)).toBeTruthy();
    expect(screen.queryByText(long)).toBeNull(); // folded
    fireEvent.click(screen.getByText('展开全文'));
    expect(screen.getByText(long)).toBeTruthy(); // expanded in full
    expect(screen.getByText('收起')).toBeTruthy();
  });

  it('offers no expander for a short answer', () => {
    render(<DeliveryCard delivery={delivery()} />);
    expect(screen.queryByText('展开全文')).toBeNull();
  });

  it('copies the delivery text and confirms it', async () => {
    render(<DeliveryCard delivery={delivery()} />);
    fireEvent.click(screen.getByText('复制'));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(delivery().content));
    expect(await screen.findByText('已复制')).toBeTruthy();
  });

  it('shows a failed delivery with its error and the run pointer', () => {
    const onOpenRun = vi.fn();
    render(
      <DeliveryCard
        delivery={delivery({ status: 'failed', content: '', error: 'ValueError: bad input' })}
        onOpenRun={onOpenRun}
      />
    );
    expect(screen.getByText('失败')).toBeTruthy();
    expect(screen.getByText(/ValueError: bad input/)).toBeTruthy();
    fireEvent.click(screen.getByText('查看执行详情'));
    expect(onOpenRun).toHaveBeenCalledWith('run-77');
  });

  it('keeps the run pointer away from a delivered answer', () => {
    const onOpenRun = vi.fn();
    render(<DeliveryCard delivery={delivery()} onOpenRun={onOpenRun} />);
    expect(screen.queryByText('查看执行详情')).toBeNull();
  });
});
