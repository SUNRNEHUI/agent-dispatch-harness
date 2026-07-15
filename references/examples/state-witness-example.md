# Production State Witness

## Symptom and terminal condition

- Symptom: imported item thumbnails remain blank while the editor shows a spinner.
- Success observable: the current token's thumbnail keys are cached and the spinner is false.

## Actual call chain

```text
user imports item -> Sources/ImportController.swift::handleImport -> Sources/EditorState.swift::updateRawPresentation -> Sources/ThumbnailGate.swift::shouldDecode -> Sources/ThumbnailStore.swift::commit -> Sources/ThumbnailCell.swift::render
```

## State inputs

| Input | Producer | Lifecycle/event | Source locator | Reported value |
|---|---|---|---|---|
| displayMode | render state | full render commit | Sources/EditorState.swift::rawDisplayMode | renderedRaw |
| presentationPending | first-frame receipt | receipt creation/consumption | Sources/EditorState.swift::rawPresentationPending | true |
| baseReady | image service | preview/base decode | Sources/ThumbnailService.swift::hasRawStyleThumbnailBase | true |
| importWindow | import lease | import tail release | Sources/ImportCoordinator.swift::importCriticalWindow | false |

## Truth table

| Case | Production state | Observed before | Expected after | Executable evidence |
|---|---|---|---|---|
| failing before | renderedRaw + presentationPending=true + baseReady=true + importWindow=false | blocked | allow thumbnail work | Tests/ThumbnailGateTests.swift::renderedRawPresentationPending |
| fixed after | renderedRaw + presentationPending=true + baseReady=true + importWindow=false | blocked | allow thumbnail work | Tests/ThumbnailGateTests.swift::renderedRawPresentationPending |
| preserved block | renderedRaw + presentationPending=true + baseReady=true + importWindow=true | blocked | blocked | Tests/ThumbnailGateTests.swift::importCriticalWindow |

## Unknowns and instrumentation

- Unknown: whether receipt consumption itself triggers a store refresh.
- Log/fixture needed: Sources/ThumbnailPipeline.swift::logGateState; queue depth, cache count, and terminal completion timing.

## Verification tier

- Required tier: user_visible
- Observed tier: flow
- Review status: pending
- Independent reviewer: thumbnail-state-reviewer
- Review evidence path: reports/state-witness-review.md
