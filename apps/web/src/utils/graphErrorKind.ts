/**
 * @file graphErrorKind
 * @description Classify backend graph-index error payloads into display kinds
 * (network / service / cancelled). Domain classification lives here, not in
 * the graph component files, so UI code never carries the classification
 * rules. Display copy lives in the graph namespace (errorKind.*).
 *
 * The regexes match Chinese keywords in backend-provided error strings on
 * purpose (classification, not display); keep them literal.
 */
import { i18n } from '@/i18n';

export function classifyErrorKind(kind: string | null | undefined, error?: string | null): string {
  if (kind === 'network') return i18n.t('graph:errorKind.network');
  if (kind === 'service') return i18n.t('graph:errorKind.service');
  if (kind === 'cancelled') return i18n.t('graph:errorKind.cancelled');
  if (error?.includes('取消')) return i18n.t('graph:errorKind.cancelled');
  if (error && /(timeout|network|连接|超时|dns|getaddrinfo)/i.test(error))
    return i18n.t('graph:errorKind.network');
  if (
    error &&
    /(engine|502|503|服务|引擎|already exists|not an empty directory|命令失败|permission|disk|quota)/i.test(
      error
    )
  ) {
    return i18n.t('graph:errorKind.service');
  }
  return i18n.t('graph:errorKind.unknown');
}
