export function parseGitHubPrLink(objectId: string): { label: string; url: string } | null {
  const match = objectId.match(/^(.+?)#(\d+)$/);
  if (!match) return null;
  return { label: `PR #${match[2]}`, url: `https://github.com/${match[1]}/pull/${match[2]}` };
}
