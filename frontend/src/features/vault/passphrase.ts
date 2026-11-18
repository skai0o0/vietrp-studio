/** Mirrors the server rule (WP-D `check_strength`); the server stays the authority. */
export const MIN_PASSPHRASE_CHARS = 16;
export const MIN_PASSPHRASE_WORDS = 4;
export const MIN_PASSPHRASE_CHARS_WITH_WORDS = 12;

export function isPassphraseStrong(passphrase: string): boolean {
  if (passphrase.length >= MIN_PASSPHRASE_CHARS) return true;
  const words = passphrase.trim().split(/\s+/).filter(Boolean);
  return (
    words.length >= MIN_PASSPHRASE_WORDS && passphrase.length >= MIN_PASSPHRASE_CHARS_WITH_WORDS
  );
}
