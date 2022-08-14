BEGIN;


CREATE TABLE IF NOT EXISTS panes (
  pane_id      TEXT    NOT NULL PRIMARY KEY,
  session_name TEXT    NOT NULL,
  window_index INTEGER NOT NULL,
  window_name  TEXT    NOT NULL,
  pane_index   INTEGER NOT NULL
) WITHOUT ROWID;


CREATE TABLE IF NOT EXISTS words (
  pane_id    TEXT      NOT NULL REFERENCES panes (pane_id) ON UPDATE CASCADE ON DELETE CASCADE,
  word       TEXT      NOT NULL,
  lword      TEXT      NOT NULL,
  UNIQUE     (pane_id, word)
);
CREATE INDEX IF NOT EXISTS words_pane_id ON words (pane_id);
CREATE INDEX IF NOT EXISTS words_word    ON words (word);
CREATE INDEX IF NOT EXISTS words_lword   ON words (lword);


END;
