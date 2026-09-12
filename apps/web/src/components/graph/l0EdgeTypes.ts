/**
 * @file l0EdgeTypes
 * @description L0 edge type catalog and legend colors, matching the edge types produced by the backend L0 pipeline.
 *
 * Functional data (edge type ids, colors, and the error-classification regexes)
 * stays literal: the error regexes match Chinese keywords in backend-provided
 * error strings on purpose (classification, not display). Display copy lives in
 * the graph namespace (edgeType.* / edge.all / errorKind.*); the `label` field
 * carries the i18n key and is translated at render sites.
 *
 * Responsibilities:
 * - Define the L0 edge type catalog and legend colors as literal data
 * - Translate edge type ids into display labels at render time
 * - Classify backend error strings into network / service / cancelled kinds
 */
import { i18n } from '@/i18n';

export const L0_EDGE_TYPES = [
  { id: 'related', label: 'graph:edgeType.related', color: '#2dd4bf' },
  { id: 'cross_repo', label: 'graph:edgeType.cross_repo', color: '#fb923c' },
] as const;

export type L0EdgeTypeId = (typeof L0_EDGE_TYPES)[number]['id'];

export const L0_EDGE_COLOR_MAP: Record<string, string> = Object.fromEntries(
  L0_EDGE_TYPES.map((edge) => [edge.id, edge.color])
);

export function labelForEdgeType(id: string | null | undefined): string {
  if (!id) return i18n.t('graph:edge.all');
  const hit = L0_EDGE_TYPES.find((edge) => edge.id === id);
  return hit ? i18n.t(hit.label) : id;
}

export function classifyErrorKind(kind: string | null | undefined, error?: string | null): string {
  if (kind === 'network') return i18n.t('graph:errorKind.network');
  if (kind === 'service') return i18n.t('graph:errorKind.service');
  if (kind === 'cancelled') return i18n.t('graph:errorKind.cancelled');
  // The regexes below classify backend error strings (Chinese keywords included); keep them literal.
  if (error && /取消/.test(error)) return i18n.t('graph:errorKind.cancelled');
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
