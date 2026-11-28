# E-M1 Mark III Mod Builder

Build a custom, unofficial firmware bundle for the Olympus **OM-D E-M1 Mark III** camera.

**Download the latest app:** https://github.com/dfeldt91-blip/E-M1-Miii/releases

> ⚠️ **This is unofficial.** Modifying and flashing your camera's firmware is done entirely at your own risk.

## What it does

- Downloads the official **version 1.6 firmware** from Olympus/OM Digital Solutions' update server and verifies it.
- Lets you pick the mods you want and builds the `E1399999.BIN` update file.
- Walks you through installing it on the camera.
- Can also build a **stock 1.6** file with no mods, if you want to go back.
- Available as a Mac or Windows app, or as a Python script from this repository.

No firmware is stored here — the mods are edit lists applied to your own download.

## What this project covers

This is for the **E-M1 Mark III only**. I don't own other camera models and can't make or test mods for them — unless, of course, you want to send me a camera to test on and pay for return shipping. If you're looking for custom firmware for another body, check the [OM Firmware Atlas](https://xulfr.github.io/om-firmware-atlas/views/cameras/).

## Latest version

The latest release has a new UI and includes:

- **Tone Curves:** a large selection added to the Gradation menu
- **Tone Curves:** two configurable custom slots via the app
- **Handheld High Res:** manual and fill flash (TTL lens required)
- **Aspect:** XPAN 65:24
- **White Border:** an Art Filter effect with adjustable border width
- **Focus Stacking:** in-camera, with all lenses
- **Auto-ISO:** starts at ISO 64 instead of ISO 200
- **Video:** recording limit raised from 29 minutes to 9 hours
- **Custom C1/C2/C3/C4:** video modes can be saved
- **Art Filter:** monochrome Key Line II
- **Custom Buttons:** more options for the right and down buttons
- **6 selectable filter slots** assigned to a Custom Picture Profile
- **Underscore** as an option in custom filenames
- **Custom text** at the top of the first menu page — I use mine for name/phone in case it's lost or stolen; it survives a factory reset
- **Digital Teleconverter** in High Res mode (best results with sharpness set low)

## Working on

- 6 Custom Picture Profiles to replace the stock profiles
- Per-profile shadow / midtone / highlight settings
- Proper tone-curve names in the SCP cell and picker Icons for each new tone curve
- Full-sensor highlight/shadow metering
- Various picture and art profile mods

## Credits

Thank you to **Caduceus**, **Fishcu**, and many others whose work helped make this possible.

## Support

I don't have PayPal or other money apps for donations, but my three Kitty Kats put together an Amazon wishlist if you'd like to show appreciation for the effort:

https://www.amazon.com/hz/wishlist/ls/1W2EOKOSMBU49
