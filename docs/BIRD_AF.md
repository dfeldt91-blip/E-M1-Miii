# Bird subject detection (AF) on the E-M1 Mark III — research

Status: **research only, not implemented.** Rated **Unlikely** in `MOD_IDEAS.md` (S24).

## What the camera already has

The E-M1 Mark III has an "Intelligent Subject Detection" AF path that is a
deep-learning pipeline, not a simple threshold:

- Setting `MODE_SUBJECT_DETECT` (id `0x693`), validator record at runtime
  `0x604e1184`: u8 list `[0, 1, 2, 3]` — i.e. **4 values only**: Off + 3
  subject types. (Decoded from the stock 1.6 firmware
  `OLY_E_139_1600_0000_0000.BIN`.)
- Debug firmware strings (block 0):
  - `DeepLearningSubjectDetect : %u` / `DeepLearningSubjectDetect:     %u`
  - `MDET_DL_SET_RGB_IMAGE_PRM parameter` with fields `mode_subject_detect`,
    `mode_aspect_ratio`, `digital_telecon`, `buff_id`, `free_run_count`.
  - `MDET_DL_RECEIVE_SUBJECT`, `MDET_RECEIVE_SUBJECT_CP`,
    `MDET_DL_SEND_IMAGE_CPU2`, `MDET_DL_END_WAIT_CPU0`,
    `mdet_laf_judge_dl_subject`, `calc_subject_region`, `calc_subject_area`,
    `save_subject_info`, `judge_subject_area_predict`,
    `judge_pass_subject_occlusion`, `subjects_num`.
- The pipeline runs on the AM (MN103) core and feeds the AF/tracking code:
  `mdet_laf_judge_dl_subject` is the AF-side consumer of the DL result.

So the E-M1 III does have a trained subject-detection model — but only for
the **3 types already in the validator list** (the menus show Off + 3). The
labels are not stored as plain ASCII in the firmware (they are icon/string-ID
driven), so the exact 3 types are not identified here; the OM System
documentation lists them as Motorsports / Airplanes / Trains on this body.

## Why "bird AF" is not a simple patch

1. **No trained model weights.** The DL result is produced by a model whose
   weights live in the firmware (most likely in the compressed main-block
   blobs or a dedicated data region). There is no bird/animal class in the
   E-M1 III's model — the validator list stops at value 3, and the AF-side
   code (`mdet_laf_judge_dl_subject`, `calc_subject_region`, …) is written
   around the existing 3 types. Adding a 4th value would require:
   - a trained bird-detection model (weights + input preprocessing), and
   - the AF/tracking integration for the new class (region prediction,
     occlusion handling, subject-area calc).
2. **Hardware / processor mismatch with OM-1.** The OM-1 (which added birds,
   dogs, cats) uses a newer processor and a newer firmware generation; its
   model format and AF pipeline are not compatible with the E-M1 III's
   MN103/AM core + ARM Cortex-A9 coprocessor. Porting weights is not
   feasible without the OM-1 firmware's format documentation.
3. **Menu / SCP / icons.** Even if the value existed, the menus, SCP cells,
   Live Control lists and icon tables (block 1, `0xa35b65d0` icon store)
   would need entries for the new subject type.

## What a patch would have to touch (for reference)

- Validator list of `MODE_SUBJECT_DETECT` (`0x604e1184`): extend
  `[0,1,2,3]` to include the new value (data-only, feasible).
- The DL pipeline (`MDET_DL_SET_RGB_IMAGE_PRM` … `DeepLearningSubjectDetect`):
  the new class must be produced by the model — **not patchable without
  weights**.
- AF consumer (`mdet_laf_judge_dl_subject`, `calc_subject_region`,
  `calc_subject_area`, `judge_subject_area_predict`,
  `judge_pass_subject_occlusion`): handle the new class.
- Menu / SCP / icon tables (compressed OSD/main blobs): labels and icons.

## Conclusion

Extending the *list* is trivial and pointless without the model and AF
integration. Per the project's own assessment this is **Unlikely** and is
left as an open research item. If a bird model ever becomes available
(e.g. from a future firmware or a community-trained model in a compatible
format), the addresses above are the entry points.

## Key addresses (stock 1.6, block 0, runtime base 0x60021020)

| Symbol / string | Runtime address |
|---|---|
| `MODE_SUBJECT_DETECT` setting | `0x693` |
| validator record | `0x604e1184` (list `0x604da3f8` = `[0,1,2,3]`) |
| `subject_detect` (debug) | `0x6046759d` (body `0x44657d`) |
| `DeepLearningSubjectDetect` | `0x6161a86c` (body `0x15f984c`) |
| `MDET_DL_SET_RGB_IMAGE_PRM` | `0x6161e6ec` (body `0x15fd6cc`) |
| `mdet_laf_judge_dl_subject` | (search body strings) |
| icon store (block 1) | `0xa35b65d0` |
