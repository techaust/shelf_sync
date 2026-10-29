// The Help panel's own words (UI-HELP; proposed (m2.5a) for 13). Apart from the guides' bodies (guides.tsx), so the
// panel and its button are in the main bundle while the guides load only when the panel shows one (the React.lazy
// split, m2.5b).

import type { GuideId } from "./helpModel";

export const H = {
  title: "Help",
  close: "Close help",
  guides: "Guides",
  allGuides: "All guides",
  open: "Help",
  copy: "Copy",
  copied: "Copied.",
  pressCtrlC: "Press Ctrl+C to copy.",
  guideTitles: {
    "shop-manager-key": "Make a Shop Manager key", // mockup
    "s3-policy": "Set up the S3 access policy (IAM)", // mockup
    "github-token": "Make a GitHub token for updates", // mockup
    "restore-database": "Restore the database from a backup", // proposed (m2.5b): the runbook's own title
  } satisfies Record<GuideId, string>,
  never: "Never paste a key into chat, a document or a screenshot. A key shown anywhere else has to be replaced.",
  // the S3 guide
  noBucket: "Fill in the bucket under Settings › Storage first. Until then the policies say BUCKET.",
  noBucketLink: "Open Storage settings",
  bucketUnknown: "ShelfSync didn't answer, so the bucket's name couldn't be filled in. Replace BUCKET with it.",
  bucketLead: "The policies below are for the bucket",
  readWriteTitle: "Read and write policy (ShelfSyncReadWrite)",
  readOnlyTitle: "Read-only policy (ShelfSyncReadOnly)",
  policyLabel: (title: string) => `${title}, JSON`,
  // the restore guide (proposed (m2.5b)): its two commands' titles and their name for screen readers
  listTitle: "List the backups",
  restoreTitle: "Restore one backup",
  commandLabel: (title: string) => `${title}, PowerShell command`,
};
