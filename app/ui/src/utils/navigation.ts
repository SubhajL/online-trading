/**
 * Navigation utility functions for consistent active state logic
 * across Header and Sidebar components.
 */

/**
 * Determines if a navigation link should show active state.
 *
 * @param currentPath - Current pathname from usePathname() or null during SSR
 * @param targetPath - The path this navigation link points to
 * @returns true if the link should be marked as active
 *
 * Rules:
 * - Root path ('/') requires exact match
 * - Other paths match if current path starts with target path
 * - Returns false if currentPath is null/undefined (SSR safety)
 */
export function isPathActive(currentPath: string | null | undefined, targetPath: string): boolean {
  if (!currentPath) {
    return false
  }

  if (targetPath === '/') {
    return currentPath === '/'
  }

  return currentPath === targetPath || currentPath.startsWith(`${targetPath}/`)
}

/**
 * Generates navigation link className with conditional active state.
 *
 * @param currentPath - Current pathname from usePathname() or null during SSR
 * @param targetPath - The path this navigation link points to
 * @param baseClass - Base CSS class name for the link
 * @returns Space-separated class names including 'active' if path matches
 */
export function getNavLinkClassName(
  currentPath: string | null | undefined,
  targetPath: string,
  baseClass: string,
): string {
  const active = isPathActive(currentPath, targetPath)
  return active ? `${baseClass} active` : baseClass
}
