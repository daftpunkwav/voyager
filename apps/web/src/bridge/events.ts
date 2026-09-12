/**
 * @file events.ts
 * @description Event type constants, aligned with the backend platform_contracts.DomainEvent.
 */

export const EventType = {
  /** User message sent to an agent (delivered via the gateway chat) */
  USER_MESSAGE: 'user.message',
  /** Agent reply */
  AGENT_MESSAGE: 'agent.message',
  /** Agent needs user interaction (dialog/choice/confirmation) */
  AGENT_ASK: 'agent.ask',
  /** Agent asks the frontend to navigate */
  AGENT_NAVIGATE: 'agent.navigate',
  /** Service health state transition (data source of the badge bar) */
  SERVICE_HEALTH_CHANGED: 'service.health.changed',
  /** Task lifecycle (long-running task progress) */
  TASK_COMPLETED: 'task.completed',
} as const;

export type EventTypeValue = (typeof EventType)[keyof typeof EventType];
