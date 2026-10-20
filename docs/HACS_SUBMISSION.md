# Official HACS catalog submission preparation

Installing the public repository as a HACS custom repository does not place it in the default catalog. No catalog pull request is submitted automatically. The maintainer must review the draft and authorize submission.

The current [official submission rules](https://www.hacs.xyz/docs/publish/include/) require a public GitHub repository that works as a custom repository, passing HACS Action with no ignores and Hassfest, and a GitHub release created after those checks pass. The owner or a major contributor submits the PR. This standalone `isapi_vision` integration does not override a Core integration or serve as a beta replacement for one.

| Requirement | Preparation |
| --- | --- |
| Repository | `RealBlueSky227/ha-isapi-vision`; public, active, described, topics configured, issues enabled. |
| Packaging | One integration in `custom_components/isapi_vision`; all runtime files included, valid manifest/hacs.json. |
| License / branding | Existing MIT license preserved; bundled `brand/icon.png` and variants. |
| Validation | Official HACS Action without an `ignore` input, plus Hassfest and regression suites. Link the exact green run used for release. |
| Release | `v0.1.0b1`, title ISAPI Vision v0.1.0 Beta 1, GitHub **prerelease**, created only after required checks pass. |
| Domain conflict | `isapi_vision` is independent; default-repository validation must also verify no conflict with current/upcoming Core integrations. |
| Submission | Review first; add the repository string to the JSON `integration` list in `hacs/default`, preserving alphabetical order. |

The official requirements do not say that every standalone community beta is ineligible; the exclusion concerns testing/replacing Core integrations. Maintainers still decide acceptance. Beta status, limited physical hardware coverage and outstanding real-event acceptance must be disclosed honestly.

## Review-ready PR text template

Title: **Add ISAPI Vision**

```markdown
## Checklist
- [x] I've read the publishing documentation.
- [x] I've added the HACS action to my repository.
- [x] I've added the Hassfest action to my repository.
- [x] The actions pass without disabled checks.
- [x] I've linked the successful action run below.
- [x] I've created a GitHub release after successful validation.

## Links
Current release: https://github.com/RealBlueSky227/ha-isapi-vision/releases/tag/v0.1.0b1
Successful HACS action: INSERT_EXACT_RELEASE_VALIDATION_RUN_URL
Successful Hassfest action: INSERT_EXACT_RELEASE_VALIDATION_RUN_URL

ISAPI Vision is a local, read-only, push-based camera integration using ISAPI.
It is a community beta developed on ANNKE FCD600 / I51HD, firmware V5.8.10.
Other Hikvision-style ISAPI hardware is experimental. It uses its own domain
and does not override a Home Assistant Core integration. I own the repository.
```

Before submission, replace the run placeholders with the exact successful release-commit run, recheck the upstream PR template/rules, confirm ownership/checklist assertions, and apply the single sorted-list addition from a new branch based on upstream `master`. Enable maintainer edits. Do not request reviews or submit from an organization fork; follow the upstream instructions.
