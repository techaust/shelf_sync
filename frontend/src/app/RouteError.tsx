import { ChunkFailed } from "../components/ChunkBoundary";

const reload = () => window.location.reload();

/**
 * The routes' last guard (m2.5b round 1), in place of React Router's own error page, which would replace the whole app
 * and show the error's text (a file address). Under the AppShell route the shell stays and only the screen shows the
 * line; `bare` is the root's guard, for an error in the shell itself.
 */
export function RouteError({ bare = false }: { bare?: boolean }) {
  if (bare) {
    return (
      <div className="gate">
        <div className="gate__panel">
          <ChunkFailed onReload={reload} />
        </div>
      </div>
    );
  }
  return (
    <div className="page">
      <ChunkFailed onReload={reload} />
    </div>
  );
}
