# Sortling UI & Design Principles

## 1. Discord UI Buttons & Interactive Controls
- **NO EMOJIS ON BUTTON LABELS**: Discord UI Buttons (`nextcord.ui.Button`) MUST NOT contain any emojis in their `label` property under any circumstances (e.g., use `"Register Now!"` instead of `"Register Now! 🚀"`).
- Button labels must be concise, text-only, and professional.

## 2. Text-Based Emoji Prohibition Across All Embeds
- **NO EMOJIS IN EMBEDS**: Do not use emojis in embed titles, field names, or descriptions.
- **Numbered Points**: Use code ticks for numbered rank indicators (e.g. `1`, `2`, `3` instead of `[1]` or `🥇`).
- Use clean ASCII / Unicode characters for hierarchy and bullet points: `->`, `>`, `•`, `|`, `[Official]`, `[Verified]`.

## 3. Visual Hierarchy, Headers & Dividers in Embeds
- **Subheadings**: Subheadings inside embeds must use Discord Header 2 (`## Subheading Title`) so they are visually larger than body text, but smaller than the main embed title (`# Title`).
- **Visible Dividers**: Separate distinct sections using crisp heavy horizontal divider lines (`━━━━━━━━━━━━━━━━━━━━━━━`) to prevent wall-of-text clutter.
- **Bulleted Metadata Under Subheadings**: All metadata key-value pairs (e.g. Organizer, Category, Type, Dates) MUST be formatted as clean bullet lists (`• **Key**: Value`) placed under an appropriate `## Subheading Title` (e.g. `## Event Overview`, `## Club Overview`, `## Details & Schedule`), NEVER piped on a single inline line.

## 4. University Workspace & Mahindra Isolation Rule
- **Mahindra University Slug Isolation**: Mahindra University (`slug: "mahindra"`) is a unique, dedicated university workspace.
- **NEVER USE MAHINDRA DATA AS FALLBACK**: Mahindra seed data (`mahindra_clubs.html`, `mahindra_seed.json`) MUST NEVER be used as a fallback, default, or auto-seed for any other guild or university server under any circumstances.
- Dummy or custom university servers start with clean empty registries. Administrators populates their directory via website crawling or manually using `/admin add_club`.

## 5. Color Palette & Web Styling
- **Brand Colors**: Web UI strictly uses `#000543` (Deep Midnight Blue) and `#ffffff` (White).
- **Control Styling**: Web navigation buttons (`.nav-tab`) use `background: transparent` with `border: 1px solid #ffffff`.
- **Bot Embed Color**: Embeds use `BRAND_COLOR` (`0x000543`).

## 5. Embed Layout & Encapsulation
- Keep status notices, feedback confirmations, and refined profile updates inside `embed.description`.
- Place mascot thumbnails (`thinking.gif` / `Icon_Neutral.png`) inside the embed card via `embed.set_thumbnail(url=...)`.

## 6. GIF Usage Rules
- `thinking.gif` is ONLY for loading and thinking steps (e.g. Step 1 / Step 2 progress embeds during crawling).
- The GIF must NEVER appear on final result embeds (success, error, publish complete, skip, etc.).
- When editing a message from a progress state to a final state, always pass `attachments=[]` so the file attachment is cleared and does not appear outside the embed.
- No GIF is needed or allowed for the final publish step or any result/confirmation embed.

## 7. Em Dash Prohibition
- Em dashes (`-`) and en dashes (`-`) are NEVER allowed anywhere in bot output: embed titles, descriptions, field names, button labels, footers, or any other user-facing text.
- Use a plain hyphen (`-`) or restructure the sentence instead.
