# Slipstream pipeline

One app at a time, from a researched idea to an App Store submission. Claude Code does the work. You approve at the gates and do the parts only you can do.

## One-time setup (you)

1. Apple Developer Program account (paid, yearly). Needed before anything can go on the App Store. Apple checks your identity, so allow a few days.
2. Expo account at expo.dev, then `npm install -g eas-cli` and `eas login`.
3. Node.js (current LTS) and Python 3 on the machine you use with Claude Code.
4. This repo cloned locally, opened in Claude Code.

You do not need a Mac. Expo's cloud builds make the iOS app for you.

## Starting an idea

1. Do the research in the Slipstream Finder page until the idea card says Go or Go carefully.
2. Copy `ideas/_template` to `ideas/<short-name>`.
3. Paste the card into `idea-card.md`.
4. Tell Claude Code: "Start the pipeline for ideas/<short-name>."

Claude will work through the stages in `CLAUDE.md` and stop at each gate.

## Your jobs

- Approve the plan before any code is written.
- Create the app record in App Store Connect when Claude asks.
- Say yes in chat before each submission, then answer Apple's review questions and press submit for review.
- Fill in `measure.md` at day 30, 60 and 90.

## What Claude will not do

Submit for you, sign in for you, accept store agreements, or start a second app while the first is unmeasured. The last one protects your developer account. Both stores reject apps that are near-copies of what is already there.

## Android

Added later from the same code. It needs a closed test with 12 testers for 14 days first, so it is worth starting that wait once the iOS app is in review.
