/**
 * @file user
 * @description Derives avatar initials from a username.
 *
 * Falls back to 'G' (guest) when the username is missing; output is
 * uppercased for direct UI display.
 */
export function userInitials(username?: string | null): string {
  if (!username) return 'G';
  return username.slice(0, 2).toUpperCase();
}
