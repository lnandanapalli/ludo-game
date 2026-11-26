export const ROUTES = ['/', '/rules', '/about', '/account'] as const
export type Route = typeof ROUTES[number]

export function currentRoute(): Route {
  return (ROUTES as readonly string[]).includes(location.pathname) ? location.pathname as Route : '/'
}

export function navigate(path: Route) {
  if (location.pathname !== path) history.pushState(null, '', path)
  window.dispatchEvent(new PopStateEvent('popstate'))
  window.scrollTo(0, 0)
}
