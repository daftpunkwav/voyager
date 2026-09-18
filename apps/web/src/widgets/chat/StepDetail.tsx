/**
 * @file StepDetail
 * @description Expandable fact sheet for one trajectory step: tool calls show
 * status, arguments, latency and outcome; model rounds show usage and timing.
 * Shared by the process timeline and the trajectory view.
 */

import { useTranslation } from 'react-i18next';
import { toolLabel } from '@/widgets/chat/TurnTrace';
import { ChatMarkdown } from '@/widgets/chat/ChatMarkdown';
import type { TurnStep } from '@/stores/chatStore';
import { formatCompactCount } from '@/utils/trajectory';

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="chat-stepdetail__row">
      <span className="chat-stepdetail__key muted">{k}</span>
      <span className="chat-stepdetail__val">{v}</span>
    </div>
  );
}

export function StepDetail({ step }: { step: TurnStep }) {
  const { t, i18n } = useTranslation('chat');
  const isTool = step.kind === 'tool';
  const status = step.ok === false ? t('chat:traj.statusFail') : t('chat:traj.statusOk');
  // Model badge matches the row label (思考 for rounds); plan/branch-style
  // steps keep their own names since they are not thinking rounds.
  const modelBadge = step.round !== undefined ? t('chat:proc.think') : toolLabel(step.name, t);
  const listSep = i18n.language === 'zh-CN' ? '、' : ', ';
  return (
    <div className="chat-stepdetail small">
      <div className="chat-stepdetail__row">
        <span
          className={`chat-stepdetail__badge${step.ok === false ? ' chat-stepdetail__badge--fail' : ''}`}
        >
          {isTool ? status : modelBadge}
        </span>
        {typeof step.ms === 'number' ? (
          <span className="muted">
            {t('chat:traj.latency')}: {step.ms}ms
          </span>
        ) : null}
      </div>
      {isTool ? (
        <>
          <Row k={t('chat:traj.toolName')} v={toolLabel(step.name, t)} />
          {step.toolCallId ? <Row k={t('chat:traj.callId')} v={step.toolCallId} /> : null}
          {step.args ? (
            <div className="chat-stepdetail__row">
              <span className="chat-stepdetail__key muted">{t('chat:traj.args')}</span>
              <pre className="chat-stepdetail__args">{step.args}</pre>
            </div>
          ) : null}
          {step.summary ? <Row k={t('chat:traj.result')} v={step.summary} /> : null}
          {step.truncated ? (
            <div className="chat-stepdetail__note muted">{t('chat:traj.truncated')}</div>
          ) : null}
        </>
      ) : (
        <>
          {typeof step.round === 'number' ? (
            <Row k={t('chat:traj.round')} v={String(step.round)} />
          ) : null}
          {step.text ? (
            <div className="chat-stepdetail__thinkwrap">
              <span className="chat-stepdetail__key muted">{t('chat:traj.thinking')}</span>
              <div className="chat-stepdetail__think chat-md">
                <ChatMarkdown content={step.text} runCode={false} />
              </div>
              {step.textTruncated ? (
                <div className="chat-stepdetail__note muted">{t('chat:traj.thinkTruncated')}</div>
              ) : null}
            </div>
          ) : null}
          {step.reasoning ? (
            <div className="chat-stepdetail__thinkwrap">
              <span className="chat-stepdetail__key muted">{t('chat:traj.reasoning')}</span>
              <div className="chat-stepdetail__think chat-md">
                <ChatMarkdown content={step.reasoning} runCode={false} />
              </div>
              {step.reasoningTruncated ? (
                <div className="chat-stepdetail__note muted">
                  {t('chat:traj.reasoningTruncated')}
                </div>
              ) : null}
            </div>
          ) : null}
          {step.toolCalls && step.toolCalls.length > 0 ? (
            <Row
              k={t('chat:traj.requestedTools')}
              v={step.toolCalls.map((n) => toolLabel(n, t)).join(listSep)}
            />
          ) : null}
          {typeof step.inputTokens === 'number' || typeof step.outputTokens === 'number' ? (
            <Row
              k={t('chat:traj.tokens')}
              v={t('chat:traj.statTokens', {
                a: formatCompactCount(step.inputTokens ?? 0),
                b: formatCompactCount(step.outputTokens ?? 0),
              })}
            />
          ) : null}
          {typeof step.ttftMs === 'number' ? (
            <Row k={t('chat:traj.ttft')} v={`${step.ttftMs}ms`} />
          ) : null}
        </>
      )}
      {step.subagent ? <Row k={t('chat:traj.subagent')} v={step.subagent} /> : null}
      {step.runId ? <Row k={t('chat:traj.runId')} v={step.runId} /> : null}
    </div>
  );
}
