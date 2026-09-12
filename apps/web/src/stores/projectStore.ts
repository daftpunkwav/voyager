/**
 * @file projectStore.ts
 * @description Project list filter / pagination state plus current-page multi-selection
 * for batch operations.
 *
 * Responsibilities:
 * - Hold repo list filters, sorting, and pagination; filter or page changes
 *   reset the page number and clear the selection
 * - Map store state onto ProjectListParams via toApiParams
 * - Own current-page multi-selection for batch operations
 *
 * This module must not depend on UI-layer components.
 */
import { create } from 'zustand';
import type { ProjectListParams, ProjectProgress } from '@/api/types';

interface ProjectFilterState {
  /** List filter / pagination state */
  search: string;
  categoryId: string | null;
  language: string | null;
  progress: ProjectProgress | null;
  tagId: string | null;
  sortBy: NonNullable<ProjectListParams['sort_by']>;
  sortOrder: NonNullable<ProjectListParams['sort_order']>;
  page: number;
  pageSize: number;

  /** Project ids selected on the current page (batch operations only; not part of list queries) */
  selectedIds: string[];

  setSearch: (search: string) => void;
  setCategoryId: (id: string | null) => void;
  setLanguage: (lang: string | null) => void;
  setProgress: (progress: ProjectProgress | null) => void;
  setTagId: (id: string | null) => void;
  setSortBy: (sort: NonNullable<ProjectListParams['sort_by']>) => void;
  setSortOrder: (order: NonNullable<ProjectListParams['sort_order']>) => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  resetFilters: () => void;
  toApiParams: () => ProjectListParams;

  /** Multi-selection (current page only) */
  toggleSelected: (id: string) => void;
  setSelected: (ids: string[]) => void;
  clearSelected: () => void;
}

export const useProjectStore = create<ProjectFilterState>((set, get) => ({
  search: '',
  categoryId: null,
  language: null,
  progress: null,
  tagId: null,
  sortBy: 'imported_at',
  sortOrder: 'desc',
  page: 1,
  pageSize: 20,

  selectedIds: [],

  setSearch: (search) => set({ search, page: 1, selectedIds: [] }),
  setCategoryId: (categoryId) => set({ categoryId, page: 1, selectedIds: [] }),
  setLanguage: (language) => set({ language, page: 1, selectedIds: [] }),
  setProgress: (progress) => set({ progress, page: 1, selectedIds: [] }),
  setTagId: (tagId) => set({ tagId, page: 1, selectedIds: [] }),
  setSortBy: (sortBy) => set({ sortBy }),
  setSortOrder: (sortOrder) => set({ sortOrder }),
  setPage: (page) => set({ page, selectedIds: [] }),
  setPageSize: (pageSize) => set({ pageSize, page: 1, selectedIds: [] }),

  resetFilters: () =>
    set({
      search: '',
      categoryId: null,
      language: null,
      progress: null,
      tagId: null,
      sortBy: 'imported_at',
      sortOrder: 'desc',
      page: 1,
      selectedIds: [],
    }),

  toApiParams: () => {
    const state = get();
    return {
      search: state.search || undefined,
      category_id: state.categoryId ?? undefined,
      language: state.language ?? undefined,
      progress: state.progress ?? undefined,
      tag_id: state.tagId ?? undefined,
      sort_by: state.sortBy,
      sort_order: state.sortOrder,
      page: state.page,
      page_size: state.pageSize,
    };
  },

  toggleSelected: (id) =>
    set((state) => {
      const has = state.selectedIds.includes(id);
      return {
        selectedIds: has ? state.selectedIds.filter((x) => x !== id) : [...state.selectedIds, id],
      };
    }),

  setSelected: (ids) => set({ selectedIds: ids }),

  clearSelected: () => set({ selectedIds: [] }),
}));
