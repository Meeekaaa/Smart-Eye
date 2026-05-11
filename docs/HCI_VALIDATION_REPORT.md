# HCI Validation Report - Smart Eye

Date: 2026-05-05  
Project: Smart Eye, an intelligent safety surveillance system  
Application type: Desktop application built with Python and PySide6  
Evaluated scope: Login, Live Dashboard, Camera Manager, Rules Manager, and Analytics

## 1. Executive Summary

This HCI validation evaluates Smart Eye's usability using modern AI-assisted product evaluation practices inspired by Hotjar, Survicate, UserTesting, and Marker.io. Since Smart Eye is a desktop application rather than a website, web-only tracking widgets such as Hotjar and Marker.io cannot be embedded directly without redesigning the app as a web app. Instead, the evaluation applies the same HCI methods behind those tools: task-based observation, AI-assisted feedback summarization, friction-point detection, visual issue annotation, and severity-based usability reporting.

Overall result: Smart Eye has a strong operational layout for a surveillance/control-room workflow. The main navigation is understandable, key modules are separated clearly, and important system states such as alarms, camera status, and analytics are visible. The highest-priority usability risks are discoverability of setup steps, lack of inline guidance for high-risk actions, possible information density in analytics, and limited user-facing feedback when background operations fail or take time.

## 2. Tools and AI Trends Used

The evaluation used a hybrid method based on the following current usability tools and trends:

| Tool / trend | How it was applied to Smart Eye |
|---|---|
| UserTesting-style task evaluation | Defined realistic user tasks, then evaluated success, friction, confidence, and error risk. |
| Survicate-style AI survey analysis | Created a short post-task survey and grouped likely responses into themes such as setup confusion, confidence, and dashboard clarity. |
| Marker.io-style issue reporting | Recorded UI issues as annotated bug/UX cards with severity, screen, evidence, and recommended fix. |
| Hotjar-style friction analysis | Used task-flow review and UI inspection to identify drop-off points, dead ends, and unclear next actions. |
| AI-assisted heuristic review | Used Nielsen usability heuristics plus AI summarization to cluster findings into actionable priorities. |

Relevant current tool capabilities:

- Hotjar Surveys now include AI-assisted survey creation and AI summary reports for identifying what users like or dislike.
- Survicate supports AI survey creation, AI text-response analysis, AI follow-up questions, and feedback categorization.
- UserTesting provides AI Insight Summary for summarizing verbal, text, and behavioral usability-test data.
- Marker.io supports visual website feedback, screenshots, annotations, technical metadata, and session replay for bug reports.

Because Smart Eye is a PySide6 desktop app, the closest practical equivalents are: in-app feedback forms, screen-recorded task sessions, annotated screenshots, structured usability logs, and AI summarization of tester notes.

## 3. Evaluation Scope

The evaluated screens were selected from the project code:

- Login: `frontend/widgets/auth_login_card.py`
- Main navigation: `frontend/navigation.py`
- Live Dashboard: `frontend/pages/dashboard/_page.py`
- Camera Manager: `frontend/pages/camera_manager/_page.py`
- Rules Manager: `frontend/pages/rules_manager/_page.py`
- Analytics: `frontend/pages/analytics/_page.py`

These screens cover the main user journey: sign in, monitor cameras, configure cameras, configure rules, and review analytics.

## 4. User Personas

| Persona | Goal | Risk if usability fails |
|---|---|---|
| Security operator | Monitor live feeds and respond to alarms quickly. | Missed or delayed response to safety event. |
| System administrator | Add cameras, rules, models, users, and notifications. | Misconfigured surveillance pipeline. |
| Safety manager | Review analytics and export reports. | Incorrect operational conclusions or incomplete reporting. |

## 5. Test Tasks

| Task ID | Task | Expected success criteria |
|---|---|---|
| T1 | Sign in to the system. | User understands required credentials and can recover/reset password if needed. |
| T2 | Start all cameras from Live Dashboard. | User can identify the Start All action and confirm camera status. |
| T3 | Add a new camera. | User can find Camera Manager, open Add Camera, and understand required source format. |
| T4 | Add a new detection rule. | User can create a rule with conditions, action, camera scope, and alarm escalation. |
| T5 | Check analytics and export a PDF. | User can filter data, apply filters, and export a report. |

## 6. Evaluation Results

Scoring scale: 1 = poor, 5 = excellent.

| Criterion | Score | Notes |
|---|---:|---|
| Learnability | 3.5 / 5 | Navigation labels are clear, but first-time setup flow is not guided enough. |
| Efficiency | 4 / 5 | Frequent actions such as Start All, Stop All, Add Camera, Add Rule, Apply, and Export PDF are visible. |
| Error prevention | 3 / 5 | High-impact actions exist, but more confirmation, validation, and examples are needed. |
| Feedback and system status | 3.5 / 5 | Dashboard status and alarms are visible, but loading/failure states could be more descriptive. |
| Accessibility | 3 / 5 | UI is visually consistent, but icon-only meanings, keyboard flow, contrast, and screen-reader labels need validation. |
| Satisfaction | 3.5 / 5 | The app feels professional and task-focused, but complex configuration screens may overwhelm new users. |

Overall usability score: 3.4 / 5.

## 7. Key Findings

### Finding 1: First-time setup needs a guided path

Severity: High  
Affected screens: Dashboard, Cameras, Rules, Settings  
Evidence: The Dashboard provides Start All / Stop All actions, while setup actions are distributed across Cameras, Rules, Models, Notifications, and Settings. A new user may not know the correct order: add camera, load model, create rule, configure notifications, start camera.

Recommendation:

- Add a setup checklist or empty-state guide on Dashboard.
- Suggested steps: Add camera, verify model, create rule, configure notification, start monitoring.
- Show completion status for each step.

### Finding 2: Camera source input needs stronger help and validation

Severity: High  
Affected screen: Camera Manager  
Evidence: The Add Camera flow uses a source placeholder such as `rtsp://... or 0 for webcam`. This is useful, but users may still enter invalid RTSP links, unsupported local indexes, or unavailable streams.

Recommendation:

- Add inline examples for webcam, RTSP, and video file sources.
- Add a "Test connection" button before saving.
- Display clear error messages such as "Camera unavailable", "Invalid RTSP URL", or "Authentication failed".

### Finding 3: Rule creation is powerful but cognitively heavy

Severity: High  
Affected screen: Rules Manager  
Evidence: Rule creation includes logic, action, camera, priority, active state, conditions, and alarm escalation. This is appropriate for advanced users but may be difficult for first-time administrators.

Recommendation:

- Add rule templates such as "No helmet", "Unauthorized person", "Restricted area", and "Log only".
- Add a live rule summary before saving, for example: "If object = person on all cameras, trigger level 2 alarm."
- Keep the existing Simulate feature and make it more prominent after the user edits a rule.

### Finding 4: Dashboard empty states are helpful but could be more actionable

Severity: Medium  
Affected screen: Live Dashboard  
Evidence: The Dashboard includes messages such as "No cameras started" and "No active alarms". These explain the current state, but they do not always guide the next action.

Recommendation:

- When no cameras are running, show actions for "Start All" and "Add Camera".
- When no cameras exist, point users to Camera Manager.
- When cameras fail, show the reason and recovery action.

### Finding 5: Analytics filter bar may be dense

Severity: Medium  
Affected screen: Analytics  
Evidence: Analytics includes alarm level, gender, time mode, camera, rule, date range, Apply, and Export PDF in one toolbar. This is efficient for expert users but may be visually dense.

Recommendation:

- Group filters into "Event", "Camera/rule", and "Date/time".
- Add a visible "filters applied" summary.
- Disable Export PDF or show a warning when no data matches the selected filters.

### Finding 6: Some icons and abbreviations may reduce clarity

Severity: Medium  
Affected screen: Navigation  
Evidence: Navigation includes short labels such as "Notifs" and icon-based sections. New users may not immediately understand all labels.

Recommendation:

- Rename "Notifs" to "Notifications" if space allows.
- Add tooltips for all navigation items.
- Keep section grouping, because Monitor / Configure / Insights is a good mental model.

### Finding 7: Login recovery is present but needs stronger guidance

Severity: Low to Medium  
Affected screen: Login  
Evidence: The login card includes "Keep me logged in" and "Reset password", which is good. The subtitle says accounts are created in Settings > Accounts, but a locked-out user may not be able to access Settings.

Recommendation:

- Add a recovery explanation for administrators.
- Make error messages specific: invalid email format, unknown account, wrong password, account disabled.
- Confirm whether "Keep me logged in" is appropriate for shared surveillance workstations.

## 8. AI-Assisted Feedback Summary

The following themes were generated from the task walkthrough notes using an AI-style summarization method similar to Survicate/UserTesting insight clustering.

| Theme | Sentiment | Evidence | Priority |
|---|---|---|---|
| Clear main navigation | Positive | Dashboard, Cameras, Rules, Analytics are easy to locate. | Keep |
| Setup uncertainty | Negative | User may not know what to configure first. | High |
| Strong operational dashboard | Positive | Start/Stop, live feeds, alarms, and performance are visible. | Keep |
| Complex rule configuration | Mixed | Powerful but requires domain knowledge. | High |
| Dense analytics controls | Mixed | Efficient for experts, heavy for new users. | Medium |
| Need better recovery/error states | Negative | Camera/model/rule failures need plain-language recovery. | High |

## 9. Marker.io-Style Issue Cards

| Issue ID | Screen | Severity | Description | Recommended action |
|---|---|---|---|---|
| UX-001 | Dashboard | High | No guided setup path for first-time users. | Add onboarding checklist and setup completion status. |
| UX-002 | Camera Manager | High | Camera source entry can fail without enough guidance. | Add examples, validation, and Test Connection. |
| UX-003 | Rules Manager | High | Rule creation has many fields and concepts. | Add templates, live summary, and post-edit simulation prompt. |
| UX-004 | Analytics | Medium | Filter toolbar is dense. | Group filters and summarize applied filters. |
| UX-005 | Navigation | Medium | "Notifs" abbreviation may be unclear. | Rename or add tooltip. |
| UX-006 | Login | Medium | Recovery path may be unclear if admin is locked out. | Add recovery instructions and specific errors. |

## 10. Recommended Survey

Use Survicate, Zonka Feedback, Google Forms, or an in-app PySide feedback dialog after each task.

Questions:

1. How easy was it to complete the task? Scale 1-5.
2. What confused you most?
3. Did the screen clearly show what to do next? Yes / No / Partly.
4. How confident are you that your configuration was saved correctly? Scale 1-5.
5. What would you improve first?

AI analysis prompt:

```text
Summarize these usability-test responses into themes. For each theme, identify sentiment, affected screen, severity, supporting quote, and recommended UI change. Do not invent findings that are not supported by the responses.
```

## 11. Recommendations Roadmap

| Priority | Improvement | Expected HCI impact |
|---|---|---|
| P1 | Add first-run setup checklist | Improves learnability and reduces configuration errors. |
| P1 | Add Test Connection for cameras | Improves error prevention and user confidence. |
| P1 | Add rule templates and live rule summary | Reduces cognitive load in the most complex workflow. |
| P2 | Improve dashboard empty/error states | Improves visibility of system status and recovery. |
| P2 | Simplify Analytics filter presentation | Improves efficiency for safety managers. |
| P3 | Add tooltips and accessibility labels | Improves accessibility and discoverability. |

## 12. Conclusion

Smart Eye is usable for experienced operators and administrators, especially because the main sections are logically separated and the dashboard focuses on monitoring, alarms, and performance. The largest HCI opportunity is onboarding: users need clearer guidance when configuring the system for the first time. Adding setup guidance, validation, templates, and better recovery messages would raise the usability score from approximately 3.4/5 to an estimated 4.2/5.

## 13. References

- Hotjar Surveys / Contentsquare: https://www.hotjar.com/product/surveys
- Hotjar Feedback and Surveys changes: https://help.hotjar.com/hc/en-us/articles/25414886919319-Changes-to-Feedback-and-Surveys
- Survicate AI surveys: https://survicate.com/software/ai-survey/
- Survicate AI follow-up questions: https://survicate.com/features/ai-follow-ups/
- UserTesting AI Insight Summary: https://help.usertesting.com/hc/en-us/articles/13268691111453-AI-insight-summary
- UserTesting analytics and visualizations: https://help.usertesting.com/hc/en-us/articles/11880400532509-UserTesting-Analytics-and-Visualizations-Overview
- Marker.io website feedback and bug reporting: https://marker.io/
- Marker.io bug tracking: https://marker.io/website-bug-tracking
