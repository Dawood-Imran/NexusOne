---
name: ui-professional-design
description: professional ui review and implementation guidance for web applications, especially company ai chatbot products. use when designing, reviewing, or improving frontend screens, components, layouts, visual hierarchy, responsive behavior, accessibility, and overall product polish so the interface does not look generic or ai-generated.
---

# UI Professional Design Skill

Use this skill when creating or reviewing interface work for the company AI chatbot.

## Design Standard

Create a restrained, credible company product. The UI should feel designed by an experienced product team, not generated from a generic template.

## Review Checklist

### Layout
- Use clear page structure: app shell, navigation, main workspace, contextual panel only when useful.
- Keep spacing consistent with a small spacing scale.
- Align content deliberately. Avoid random centered sections.
- Ensure mobile, tablet, and desktop layouts are usable.

### Typography
- Use a limited type scale.
- Make hierarchy clear through size, weight, spacing, and grouping.
- Avoid excessive bold text.
- Keep line lengths readable.

### Color and Visual Style
- Use color sparingly for status, emphasis, and brand identity.
- Avoid generic neon gradients, glassmorphism, decorative blobs, and template-like AI visuals unless explicitly required.
- Ensure contrast is readable.
- Use restrained shadows, borders, and surfaces.

### Components
- Buttons must have clear primary, secondary, disabled, loading, and focus states.
- Inputs must have labels, validation, helper text where useful, and error states.
- Cards must group meaningful information, not decorate empty space.
- Navigation must show current location and role-aware options.

### Chat Experience
- User and assistant messages must be visually distinct.
- Loading state should communicate progress without pretending certainty.
- Denied-answer state must be calm, clear, and non-leaky.
- Errors must explain what happened and offer a next action.
- Long answers should remain readable.

### Role Awareness
- Show role context when it helps the user understand available actions.
- Do not expose restricted navigation to unauthorized roles unless requirements explicitly call for visible but disabled items.
- Permission denial must not reveal confidential details.

### Accessibility
- Use semantic HTML.
- Preserve keyboard navigation.
- Include visible focus states.
- Ensure interactive controls have accessible names.
- Avoid color-only status communication.

## Professional Polish Rules

Before marking UI complete, verify:

- No placeholder copy remains.
- No obvious template text remains.
- Empty states are useful.
- Loading states are implemented.
- Error states are implemented.
- Denied states are implemented.
- Layout does not break at common viewport sizes.
- Component styling is consistent.
- Copy is specific to the company chatbot product.

## Output Expected From Review

When reviewing UI, produce:

1. Critical issues that block completion.
2. Visual polish issues.
3. Accessibility issues.
4. Specific file/component changes required.
5. Tests or Playwright checks that should verify the fix.
