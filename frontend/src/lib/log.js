// Dev-only error logger: observable in devtools during development, silent in production builds.
export function logError(context, error) {
  if (process.env.NODE_ENV !== "production") {
    // eslint-disable-next-line no-console
    console.error(context, error);
  }
}
