# organize-notes

The workflow for organizing material into a note:

1. List the steps with `todowrite` (action=set): extract key points → draft → link;
2. Create the note with `notes__create_note` (title = topic, body in sections); write everything down before polishing — never lose key points;
3. Link related notes with `notes__link_note`; do not pile up tags as a substitute for structure;
4. Finish with `todowrite` (action=query) to confirm every item is done, then report the note id and structure to the user.
