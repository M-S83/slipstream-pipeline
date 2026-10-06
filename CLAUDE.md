# Slipstream pipeline

This repo takes one app idea at a time from research to a store submission. Mike (the owner) approves at every gate. Claude does the work between gates.

## Rules that never bend

- One idea in flight at a time. Before starting a new one, check `ideas/*/STATUS.md`. If another app is not yet live and measured, stop and say so.
- Never submit a build to a store. Prepare everything, run the pre-submit checklist, then stop at "ready to submit" and tell Mike what to click.
- Never ask for, type or store passwords, API keys, tokens, card details or ID documents in chat or in the repo. Secrets live in EAS secrets or environment variables. Mike signs in himself.
- Never create store accounts, accept store agreements or accept terms for Mike.
- Do not write fake reviews, invented download counts or made-up awards in any listing copy.
- The one-sentence difference from the idea card must be visible in the app name, subtitle or first screenshot. If it is not, the listing is not ready. Both stores reject near-copies of apps already on the store.
- If a figure cannot be checked, say so. Do not fill a gap with a plausible number.
- Writing for Mike (README text, listing copy, privacy policy, messages): plain direct prose. No corporate or AI-sounding vocabulary, no em dashes, no bold lead-ins on every point.

## Folder layout

```
ideas/
  _template/          copy this for each new idea
  <slug>/
    STATUS.md         current stage and what is waiting on whom
    idea-card.md      pasted from the Slipstream Finder page
    PLAN.md           the one job, features, leave-outs, money, screens
    listing.md        store text, with the character limits
    release-checklist.md
    measure.md        figures at day 30, 60, 90
    app/              the Expo project
tools/
  chart_scan.py       top grossing apps per category with a modest number of ratings
  store_check.py      top 10 App Store results for a keyword
  review_check.py     counts complaints in recent low-star App Store reviews for an app
```

## Stages

Update `STATUS.md` at the end of every stage: stage name, date, what is done, what is blocked and on whom.

1. Intake. Mike pastes the idea card (Copy the card as text, on the Slipstream Finder page) into `idea-card.md`. Read the verdict. Only "Go" or "Go carefully" continues. "Stop or switch" or "Not finished yet" stops here and says what is missing.
2. Refresh the store check. Run `python tools/store_check.py "<keyword>"` on Mike's machine and compare with the card. If the top 10 now looks harder than the card says, say so before going further. Then run `python tools/review_check.py "<parent app>" "<top competitor>" --country gb,us` and read `review_check.md`. A gap counts only if it repeats across several low-star reviews, and the example quotes must be read, because the counts are keyword matches. Revenue and download estimates still come from a research tool by hand (Appfigures, AppMagic); no free source has them.
3. Plan. Write `PLAN.md`: the one job in one sentence, at most three features, what is left out, the money model, and a screen-by-screen list. GATE: Mike approves the plan in chat before any code is written.
4. Build. Create the app in `ideas/<slug>/app/` with Expo and TypeScript (`npx create-expo-app`). Keep to the plan. If a feature is not in `PLAN.md`, do not add it. Subscriptions, if the plan has them, go through RevenueCat (`react-native-purchases`), which needs an EAS development build, not Expo Go. Run the app and check every screen in `PLAN.md` works before moving on.
5. Listing. Fill `listing.md` using the limits in that file. Generate the icon (1024 by 1024) and screenshots from the real running app. Write a privacy policy that matches what the app actually collects. Host it somewhere Mike controls and put the URL in `listing.md`.
6. Pre-submit. Work through `release-checklist.md`. Every box needs a real check, not an assumption. Anything unchecked goes into `STATUS.md` as a blocker.
7. Submit. GATE: Mike says yes in chat for this submission. Then `eas build --platform ios --profile production`, then `eas submit --platform ios`. Mike has to have the Apple Developer account, the app record in App Store Connect and `eas login` done first. Claude stops after the submit command and tells Mike to complete the review questions and press submit for review in App Store Connect.
8. Measure. At day 30, 60 and 90 Mike fills in `measure.md` from App Store Connect. Compare revenue per install with the published medians: with a trial or hard paywall, $2.32 at day 14 and $3.09 at day 60; for a free app, $0.27 and $0.38. Do not judge before 60 to 90 days. Then decide with Mike: grow this app with the next opening, or stop. A separate app only if it is a genuinely different product.

## Android, later

Same Expo codebase. A new personal Play developer account needs a closed test with 12 testers opted in for 14 days before production access, so start that wait as soon as the iOS app is in review. As far as I know, the first upload of a new Play app has to be done by hand in Play Console. Check Google's current rules before relying on this.
