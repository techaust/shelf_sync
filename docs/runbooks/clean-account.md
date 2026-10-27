# Make the clean test account (once, before the M1b exit test)

ShelfSync's installer is tested on a second Windows account that has never had ShelfSync, Python or the repo on it ([07 §2](../07-testing.md); Windows Sandbox isn't on Windows 11 Home, 04-A V24). You make it once and keep it for later milestones.

**You do this outside the Claude app.** Claude never changes Windows security settings ([CLAUDE.md](../../CLAUDE.md) rule 12): this runbook only **reads** the Smart App Control state.

## 1. Add the account
1. Press **Windows key**, type `Other users`, open **Other users** (in Settings › Accounts).
2. Next to **Add other user**, click **Add account**.
3. Click **I don't have this person's sign-in information**.
4. Click **Add a user without a Microsoft account**.
5. User name: `ShelfSyncTest`. Set a password and the three security questions (keep them with your other passwords).
6. Click **Next**. The new account is a **Standard user**: leave it that way. The test must pass without admin rights.

## 2. Sign in to it once
1. Press **Windows key + L**, pick **ShelfSyncTest** at the bottom left, sign in.
2. Let Windows finish setting the account up (a minute or two). Decline every optional offer (privacy choices: the most private option).

## 3. Record the protection state (read only)
In the **ShelfSyncTest** account:
1. Press **Windows key**, type `Windows Security`, open it.
2. **Virus & threat protection:** note whether **Real-time protection** is On. The test needs it On; if it's Off, stop and tell Claude (don't change it for the test).
3. **App & browser control › Smart App Control settings:** note the state (On, Evaluation or Off). **Don't change it.**
4. **App & browser control › Reputation-based protection settings:** note whether **Check apps and files** (SmartScreen) is On.

Tell Claude the three states in one line, for example: "Defender on, Smart App Control off, SmartScreen on". They go into [09](../09-tooling.md) §1 and the M1b record.

## Afterwards
Sign out of ShelfSyncTest (**Start › your picture › Sign out**) and go back to your own account. Leave the account in place.
