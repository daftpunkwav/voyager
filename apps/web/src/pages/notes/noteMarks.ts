/**
 * @file noteMarks
 * @description Public entry point for note highlights: palette, scanning, writing, and the preview plugin. Implementations are split by responsibility.
 */

export {
  NOTE_HL_KIND,
  NOTE_HL_LABEL,
  NOTE_HL_TONES,
  NOTES_HL_RGB_DEFAULT,
  NOTES_HL_RGB_KEY,
  isRgbTone,
  notesHlMarkProps,
  parseHlTone,
  parseNoteHighlight,
  recoverTonedMarkup,
  rgbToneHex,
  wrapNoteHighlight,
  type NoteHlAction,
  type NoteHlTone,
} from './noteHl';
export { findMarks, scanMarks, splitBlockPrefix, type NoteMarkSpan } from './noteMarkScan';
export {
  applyNoteHighlight,
  applyNoteHighlightInDoc,
  expandHighlightRange,
  flattenMultilineMarks,
  toggleNoteHighlight,
} from './noteMarkApply';
export { NOTE_PREVIEW_REMARK, remarkNoteMarks, splitMarkedText } from './noteMarkRemark';
export { diffReplace } from './noteMarkDiff';
