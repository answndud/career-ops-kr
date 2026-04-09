You are setting the default UI design system for this project. Treat these rules as the baseline visual specification for all current and future screens unless explicitly overridden.

## DESIGN GOAL
Create a restrained, minimal, grayscale-first admin/operations dashboard style. The UI must feel calm, disciplined, highly legible, and consistent. Prioritize clarity, information density, and operational usefulness over visual flair.

## CORE VISUAL CHARACTER
- Internal admin dashboard, not a marketing site
- Neutral grayscale palette, not brand-forward
- Quiet hierarchy through typography, spacing, and layout
- Very limited accent usage
- Clean, structured, practical, and low-noise

## NON-NEGOTIABLE RULES
- Do not use gradients, glassmorphism, blur, or translucent panels
- Do not use bright SaaS-style accent colors across the layout
- Do not use heavy shadows
- Do not use oversized rounded corners
- Do not use playful, decorative, or trendy visual treatments
- Do not invent one-off component styles per screen
- Do not create a marketing/landing-page aesthetic

## COLOR SYSTEM
Use a grayscale-first palette across the entire application.

### Base colors:
- Page background: white
- Surface / card background: white
- Primary text: near-black
- Secondary text: muted gray
- Borders and dividers: subtle light gray
- Dark emphasis surface (table headers, high-emphasis controls): charcoal
- Text on dark surfaces: white or near-white

### Accent usage:
- Accent colors must be sparse and only used where functionally justified
- Status colors are allowed only for badges, chips, small indicators, or alerts
- Status colors must be muted and slightly desaturated, never neon or highly saturated

## TYPOGRAPHY
Use a clean sans-serif system stack. No decorative typography.

### Typography rules:
- Use typography to create hierarchy instead of color or decoration
- Keep line-height clean and controlled
- Avoid excessive tracking
- Keep labels understated and readable
- Numeric values should feel strong and easy to scan

## SPACING SYSTEM
Use a consistent spacing system throughout the product.

### Spacing rules:
- Maintain consistent vertical rhythm across the page
- Prefer clean grouping over excessive whitespace
- Do not make the interface feel sparse like a landing page
- Do not let spacing vary arbitrarily between similar sections

## SURFACES
Cards, panels, and containers must share one visual language.

### Surface rules:
- White background
- Subtle border
- Do not us shadow
- Medium border radius
- Do not stack multiple shadows or layered effects
- Keep surfaces flat, clean, and quiet

## LAYOUT
Use a simple desktop-first admin dashboard layout.

### Layout rules:
- Left-aligned primary content flow
- Consistent page margins and section spacing
- Favor practical density over dramatic whitespace
- Build clear horizontal and vertical alignment
- Use responsive behavior, but optimize primarily for desktop dashboard usage
- Keep information blocks structured and easy to scan

## COMPONENT RULES

### 1. Cards
- Use the shared surface style everywhere
- Titles should be modest and clear
- Content should be aligned cleanly with consistent padding

### 2. KPI / Stat cards
- Large bold numeric value
- Small muted descriptive label
- Optional small contextual note only if useful
- No decorative icons by default
- No chart embellishments unless explicitly requested

### 3. Buttons
- Primary button: dark neutral fill with light text
- Secondary button: white background, subtle border, dark text
- Keep button sizing and radius consistent with the input system
- Hover/focus states must remain subtle and professional

### 4. Inputs
- White background
- Subtle border
- Clear placeholder or label treatment
- No inset shadows
- Use a restrained focus treatment

### 5. Badges / Chips
- Small pill or rounded-rect style
- Use only for status, categorization, or lightweight metadata
- Backgrounds must be soft
- Text must remain readable
- Never use badges as decoration

### 6. Tables

### Table rules:
- Header row should use a dark background
- Header text should be light and clear
- Body rows should remain clean and readable
- Row separators should be subtle
- Avoid loud zebra striping unless explicitly requested
- Cell padding should be compact but not cramped
- Text alignment should be consistent by data type
- Long IDs, emails, or links may truncate gracefully
- Status fields should use muted badges

## INTERACTION RULES
- Use subtle hover states only
- Use subtle focus states only
- Use fast, restrained transitions only where useful
- No dramatic motion
- No flashy animation unless explicitly required for product behavior

## CONSISTENCY ENFORCEMENT
Before finishing any screen or component, verify:
- The palette remains mostly grayscale
- The same radius logic is used across cards, buttons, and inputs
- Border treatment is reused across surfaces
- Shadows remain minimal and consistent
- Typography hierarchy is driven by size and weight, not random color changes
- Status colors appear sparingly and only where semantically appropriate
- Components do not drift into different visual styles on different screens

IMPLEMENTATION REQUIREMENTS
- Define shared design tokens first
- Build reusable primitives/components next
- Build screens only from those shared primitives
- Avoid ad hoc styling inside individual screens whenever possible
- Reuse tokens for color, spacing, radius, border, shadow, and typography
- If using Tailwind, centralize repeated values through theme extension or shared utility patterns
- If using component libraries, restyle them to match this system instead of keeping their default visual identity

FINAL STANDARD
The finished product should look like a disciplined internal operations dashboard with minimal visual noise, strong readability, calm grayscale surfaces, bold metrics, dark table headers, muted status badges, and consistent spacing throughout.