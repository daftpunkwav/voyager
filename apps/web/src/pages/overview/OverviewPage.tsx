/**
 * @file OverviewPage
 * @description Overview home page: hero with Morse-animated brand art, learning progress, recent activity, recommendations, recent notes, and GitHub trending.
 *
 * Responsibilities:
 * - Compose the overview cards: learning progress, activity, recommendations,
 *   recent notes, and the trending grid with period switching
 * - Drive the trending spotlight (hover streaming, bubble width sync) and
 *   the Morse hero animation, honoring prefers-reduced-motion
 * - Render staged card entrances and safe external links for trending rows
 */

import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
} from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PRODUCT_NAME } from '@/brand';
import { useAuthStore } from '@/stores/authStore';
import {
  useActivities,
  useOverviewRecentNotes,
  useRecommendedProjects,
  useTrending,
} from '@/hooks/useOverview';
import { useProjectStats } from '@/hooks/useProjects';
import { useTrendingSpotlight } from '@/hooks/useTrendingSpotlight';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { formatRelativeTime, formatDateTime } from '@/utils/date';
import {
  abbrevCount,
  langCssClass,
  REPO_AVATAR_GRADIENTS,
  repoDisplayParts,
  splitRepoName,
} from '@/utils/format';
import { activityItemHref } from '@/utils/overviewLinks';
import { routes } from '@/utils/routes';
import { safeHttpUrl } from '@/utils/safeUrl';
import { GLASS_CHIP, GLASS_INNER, GLASS_OUTER } from '@/constants/glassTokens';
import { getMorseHopPx, HERO_MORSE_BITS, HERO_MORSE_INTERVAL_MS } from './morse';
import { AgentCarousel } from '@/components/agent/AgentCarousel';
import { TrendingSpotlight } from './TrendingSpotlight';
import type { LookTarget } from '@/components/agent/AgentAvatar';
import type { ProjectProgress, TrendingPeriod, TrendingRepo } from '@/api/types';

/** Progress rows reuse the overview:progress.* labels consumed by utils/labels.ts. */
const PROGRESS_ROWS: Array<{ key: ProjectProgress; color: string }> = [
  { key: 'none', color: 'fill-none' },
  { key: 'learning', color: 'fill-learning' },
  { key: 'learned', color: 'fill-learned' },
  { key: 'mastered', color: 'fill-mastered' },
];

const RECOMMEND_SLOT_COUNT = 5;
const ACTIVITY_SLOT_COUNT = 10;

export function OverviewPage() {
  const { t } = useTranslation('overview');
  const user = useAuthStore((s) => s.user);
  const { data: stats, isLoading: statsLoading } = useProjectStats();
  const { data: recommended = [] } = useRecommendedProjects(5);
  const { data: recentNotes = [] } = useOverviewRecentNotes(4);
  const { data: activities } = useActivities();
  const [period, setPeriod] = useState<TrendingPeriod>('weekly');
  const { data: trending = [] } = useTrending(period);

  const trendingGridRef = useRef<HTMLDivElement>(null);
  const recentNotesPanelRef = useRef<HTMLDivElement>(null);
  const [scoutBubbleWidth, setScoutBubbleWidth] = useState<number | null>(null);
  const scout = useTrendingSpotlight(period);
  const [chatBtnLookTarget, setChatBtnLookTarget] = useState<LookTarget | null>(null);
  const [morseTick, setMorseTick] = useState(0);

  useEffect(() => {
    const panel = recentNotesPanelRef.current;
    if (!panel) return;

    const syncWidth = () => {
      setScoutBubbleWidth(panel.getBoundingClientRect().width);
    };

    syncWidth();
    const ro = new ResizeObserver(syncWidth);
    ro.observe(panel);
    window.addEventListener('resize', syncWidth);

    return () => {
      ro.disconnect();
      window.removeEventListener('resize', syncWidth);
    };
  }, []);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (mq.matches) return;

    const id = window.setInterval(() => {
      setMorseTick((t) => t + 1);
    }, HERO_MORSE_INTERVAL_MS);

    return () => window.clearInterval(id);
  }, []);

  const handleChatBtnLook = (event: ReactMouseEvent<HTMLAnchorElement>) => {
    setChatBtnLookTarget({ x: event.clientX, y: event.clientY });
  };

  const handleChatBtnLookEnd = () => {
    setChatBtnLookTarget(null);
  };

  useEffect(() => {
    const grid = trendingGridRef.current;
    if (!grid || trending.length === 0) return;

    const cards = grid.querySelectorAll<HTMLElement>('.trending-card');
    cards.forEach((card) => card.classList.remove('is-visible'));

    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (mq.matches) {
      cards.forEach((card) => card.classList.add('is-visible'));
      return;
    }

    if (typeof IntersectionObserver === 'undefined') {
      cards.forEach((card) => card.classList.add('is-visible'));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const el = entry.target as HTMLElement;
          const idx = Number(el.dataset.index) || 0;
          window.setTimeout(() => el.classList.add('is-visible'), Math.min(idx * 60, 800));
          observer.unobserve(el);
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    );

    cards.forEach((card) => observer.observe(card));
    return () => observer.disconnect();
  }, [period, trending]);

  if (statsLoading) {
    return (
      <div className="overview-page page-scaffold">
        <LoadingSpinner label={t('overview:loading')} />
      </div>
    );
  }

  const total = stats?.total ?? 0;
  const byProgress = stats?.by_progress ?? {
    none: 0,
    learning: 0,
    learned: 0,
    mastered: 0,
  };
  const maxProgress = Math.max(...PROGRESS_ROWS.map((p) => byProgress[p.key] ?? 0), 1);

  const username = user?.username ?? t('overview:hero.defaultUser');
  const heroLede = user
    ? t('overview:hero.ledeBound', {
        createdAt: formatDateTime(user.created_at),
        login: user.github_login ?? 'unknown',
      })
    : t('overview:hero.ledeGuest', { count: total });

  const MIN_TREND_W = 38;
  const trendStep = trending.length > 1 ? (100 - MIN_TREND_W) / (trending.length - 1) : 0;

  const handleTrendingCardEnter = (
    repo: TrendingRepo,
    event: ReactMouseEvent<HTMLAnchorElement>
  ) => {
    scout.showForRepo(repo, { x: event.clientX, y: event.clientY });
  };

  const handleTrendingCardLeave = () => {
    scout.leaveTrendingCard();
  };

  const handleTrendingCardMove = (event: ReactMouseEvent<HTMLAnchorElement>) => {
    scout.updateLook({ x: event.clientX, y: event.clientY });
  };

  // Hero letters derive from the single brand source; must match the word in
  // morse.ts (HERO_MORSE_BITS) so the letter count aligns with the Morse bit stream.
  const heroArtChars = PRODUCT_NAME.toLowerCase().split('');

  const morseActiveIndex = morseTick % heroArtChars.length;
  const morseBit = HERO_MORSE_BITS[morseTick % HERO_MORSE_BITS.length] ?? 0;
  const morseRound = Math.floor(morseTick / HERO_MORSE_BITS.length);
  const morseInvert = morseRound % 2 === 1;

  const recommendSlots = Array.from(
    { length: RECOMMEND_SLOT_COUNT },
    (_, i) => recommended[i] ?? null
  );
  const activityItems = (activities ?? []).slice(0, ACTIVITY_SLOT_COUNT);

  return (
    <div className="overview-page page-scaffold">
      <div className="overview-hero-wrap" data-testid="overview-hero">
        <div className="overview-hero-art" aria-hidden>
          <span className="overview-hero-artword">
            {heroArtChars.map((char, index) => {
              const isMorseActive = index === morseActiveIndex;
              const hopPx = isMorseActive ? getMorseHopPx(index, morseBit, morseInvert) : 0;

              return (
                <span key={`${char}-${index}`} className="overview-hero-art-char">
                  <span
                    key={isMorseActive ? `morse-${morseTick}` : 'rest'}
                    className={`overview-hero-art-char-glyph${isMorseActive ? ' morse-hopping' : ''}`}
                    style={
                      isMorseActive ? ({ '--morse-hop': `${hopPx}px` } as CSSProperties) : undefined
                    }
                  >
                    {char}
                  </span>
                </span>
              );
            })}
          </span>
        </div>
        <div className={`overview-hero-glass ${GLASS_OUTER}`} aria-hidden />
        <section className="overview-hero-content">
          <h1>
            {t('overview:hero.greeting')}
            <span>{username}</span> 👋
          </h1>
          <p className="lede">{heroLede}</p>
          <div className="quick-actions">
            <Link
              to={routes.chat}
              className={`btn ${GLASS_INNER} liquid-glass--pulse liquid-glass-btn quick-action-brand`}
              onMouseEnter={handleChatBtnLook}
              onMouseMove={handleChatBtnLook}
              onMouseLeave={handleChatBtnLookEnd}
            >
              {t('overview:actions.chat')}
            </Link>
            <Link to={routes.sources} className={`btn ${GLASS_INNER} liquid-glass-btn`}>
              {t('overview:actions.library')}
            </Link>
            <Link to="/graph" className={`btn ${GLASS_INNER} liquid-glass-btn`}>
              {t('overview:actions.graph')}
            </Link>
            <Link to="/settings" className={`btn ${GLASS_INNER} liquid-glass-btn`}>
              {t('overview:actions.settings')}
            </Link>
          </div>
        </section>
      </div>

      <AgentCarousel externalLookTarget={chatBtnLookTarget} />

      <section className="row-2col row-2col--phi">
        <div className={`panel panel-progress ${GLASS_OUTER}`} data-testid="overview-progress">
          <h3>{t('overview:progress.title')}</h3>
          <div className="progress-panel-body">
            <section
              className={`agent-summary progress-panel-summary ${GLASS_INNER}`}
              aria-label={t('overview:summary.weeklyReportAria')}
            >
              <div className="summary-head">
                <div className={`summary-avatar ${GLASS_CHIP}`}>M</div>
                <div className="summary-meta">
                  <div className="summary-agent">{t('overview:summary.title')}</div>
                  <div className="summary-time">{t('overview:summary.autoGenerated')}</div>
                </div>
                <span className={`summary-badge ${GLASS_CHIP}`}>AI</span>
              </div>
              <div className="summary-body">
                <p>{t('overview:summary.body', { name: username })}</p>
              </div>
            </section>
            <div className="progress-overview">
              <p className="progress-section-title">{t('overview:progress.byCategory')}</p>
              <div className="progress-bars">
                {PROGRESS_ROWS.map((p) => {
                  const v = byProgress[p.key] ?? 0;
                  const pct = Math.round((v / maxProgress) * 100);
                  return (
                    <div key={p.key} className="progress-row">
                      <span className="pl">{t(`overview:progress.${p.key}`)}</span>
                      <div className="track">
                        <div
                          className={`fill ${p.color}`}
                          style={{ '--fill': pct / 100 } as CSSProperties}
                        />
                      </div>
                      <span className="pv">{v}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        <div className={`panel panel-activity ${GLASS_OUTER}`} data-testid="overview-activities">
          <div className="section-head" style={{ marginTop: 0 }}>
            <h3>{t('overview:activity.title')}</h3>
            <Link to={routes.activity} className={`more ${GLASS_INNER}`}>
              {t('overview:actions.viewAll')}
            </Link>
          </div>
          <div className="activity-list">
            {activityItems.length === 0 ? (
              <div className="panel-empty">{t('overview:activity.empty')}</div>
            ) : (
              activityItems.map((a) => (
                <Link
                  key={a.id}
                  className={`activity-item ${GLASS_INNER}`}
                  to={activityItemHref(a)}
                  data-testid="overview-activity-item"
                >
                  <div className="activity-icon">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      width={14}
                      height={14}
                    >
                      <path d="M21 15a3 3 0 0 1-3 3H8l-5 4V6a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v9z" />
                    </svg>
                  </div>
                  <div className="activity-body">
                    <div className="activity-title">{a.title}</div>
                    <div className="activity-desc">{a.description}</div>
                  </div>
                  <span className="activity-time">{formatRelativeTime(a.created_at)}</span>
                </Link>
              ))
            )}
          </div>
        </div>
      </section>

      <section className="row-2col row-2col--phi">
        <div
          className={`panel panel-recommend ${GLASS_OUTER}`}
          data-testid="overview-recommendations"
        >
          <h3 className="panel-title-with-sub">
            {t('overview:recommend.title')}
            <span className="panel-title-sub">{t('overview:recommend.subtitle')}</span>
          </h3>
          <div className="project-list">
            {recommendSlots.map((item, i) => {
              if (!item) {
                return (
                  <div
                    key={`rec-empty-${i}`}
                    className={`project-item project-item--placeholder ${GLASS_INNER}`}
                    aria-hidden
                  >
                    <div
                      className="project-avatar"
                      style={{
                        background: REPO_AVATAR_GRADIENTS[i % REPO_AVATAR_GRADIENTS.length],
                      }}
                    >
                      ·
                    </div>
                    <div className="project-info">
                      <div className="project-name">{t('overview:recommend.loading')}</div>
                      <p className="project-desc">{t('overview:recommend.loadingDesc')}</p>
                    </div>
                  </div>
                );
              }
              const { owner, repo } = repoDisplayParts(item);
              return (
                <Link
                  key={item.id}
                  className={`project-item ${GLASS_INNER}`}
                  to={item.project_id ? routes.sourceRepo(item.project_id) : routes.sources}
                  aria-describedby={`rec-reason-${item.id}`}
                  data-testid="overview-recommend-item"
                >
                  <div
                    className="project-avatar"
                    style={{ background: REPO_AVATAR_GRADIENTS[i % REPO_AVATAR_GRADIENTS.length] }}
                  >
                    {(repo[0] ?? '?').toUpperCase()}
                  </div>
                  <div className="project-info">
                    <div className="project-name">
                      {owner ? (
                        <>
                          <span className="owner">{owner}</span>
                          <span className="slash">/</span>
                        </>
                      ) : null}
                      <span>{repo}</span>
                    </div>
                    <div className="project-desc-swap">
                      <p className="project-desc">{item.description ?? ''}</p>
                      <p className="project-reason" id={`rec-reason-${item.id}`}>
                        {item.reason}
                      </p>
                    </div>
                  </div>
                  <span className="project-stars">⭐ {abbrevCount(item.stars)}</span>
                </Link>
              );
            })}
          </div>
        </div>

        <div
          className={`panel panel-notes ${GLASS_OUTER}`}
          ref={recentNotesPanelRef}
          data-testid="overview-notes"
        >
          <div className="section-head" style={{ marginTop: 0 }}>
            <h3>{t('overview:notes.title')}</h3>
            <Link to="/notes" className={`more ${GLASS_INNER}`}>
              {t('overview:actions.viewAll')}
            </Link>
          </div>
          <div className="notes-list">
            {recentNotes.length === 0 ? (
              <div className="panel-empty">{t('overview:notes.empty')}</div>
            ) : (
              recentNotes.map((n) => (
                <Link
                  key={n.id}
                  className={`note-item ${GLASS_INNER}`}
                  to={routes.note(n.id, n.project_id)}
                  data-testid="overview-note-item"
                >
                  <div className="note-title">{n.title}</div>
                  <div className="note-meta">
                    <span className="tag-link">{n.project_name}</span>
                    <span>·</span>
                    <span>{formatRelativeTime(n.updated_at)}</span>
                  </div>
                </Link>
              ))
            )}
          </div>
        </div>
      </section>

      <section className="trending-section" data-testid="overview-trending">
        <div className="trending-head">
          <div className="trending-head-left">
            <h2>{t('overview:trending.title')}</h2>
            <span className="trending-subtitle">{t('overview:trending.subtitle')}</span>
          </div>
          <div className="period-toggle glass-card glass-card--panel-clear" role="tablist">
            {(['daily', 'weekly', 'monthly'] as TrendingPeriod[]).map((p) => (
              <button
                key={p}
                type="button"
                className={`period-btn liquid-glass--pill${
                  period === p ? ` ${GLASS_INNER} active` : ''
                }`}
                onClick={() => setPeriod(p)}
              >
                {p === 'daily'
                  ? t('overview:trending.daily')
                  : p === 'weekly'
                    ? t('overview:trending.weekly')
                    : t('overview:trending.monthly')}
              </button>
            ))}
          </div>
        </div>
        <div className="trending-grid" ref={trendingGridRef}>
          {trending.length === 0 ? (
            <div className="trending-empty">{t('overview:trending.empty')}</div>
          ) : (
            trending.slice(0, 50).map((r, index) => {
              const widthPct = Math.max(100 - index * trendStep, MIN_TREND_W);
              const { owner, repo } = splitRepoName(`${r.owner}/${r.repo}`);
              return (
                <a
                  key={`${period}-${r.owner}/${r.repo}`}
                  data-index={index}
                  className={`trending-card ${GLASS_INNER}`}
                  data-testid="overview-trending-card"
                  style={{ ['--card-w' as string]: `${widthPct.toFixed(2)}%` }}
                  href={safeHttpUrl(r.url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  onMouseEnter={(event) => handleTrendingCardEnter(r, event)}
                  onMouseLeave={handleTrendingCardLeave}
                  onMouseMove={handleTrendingCardMove}
                >
                  <div className={`trending-rank ${GLASS_CHIP}`}>{r.rank ?? index + 1}</div>
                  <div className="trending-body">
                    <div className="trending-name">
                      <span className="owner">{owner}</span>
                      <span className="slash">/</span>
                      <span>{repo}</span>
                    </div>
                    <div className="trending-desc">{r.description ?? ''}</div>
                    <div className="trending-meta">
                      <span className={`lang-dot ${langCssClass(r.language)}`}>
                        {r.language ?? '-'}
                      </span>
                      <span className="stars">★ {abbrevCount(r.stars)}</span>
                    </div>
                  </div>
                </a>
              );
            })
          )}
        </div>
      </section>

      <TrendingSpotlight
        phase={scout.phase}
        repo={scout.repo}
        content={scout.content}
        isStreaming={scout.isStreaming}
        lookTarget={scout.lookTarget}
        bubbleWidthPx={scoutBubbleWidth}
      />
    </div>
  );
}
