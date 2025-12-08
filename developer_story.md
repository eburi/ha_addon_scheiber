# The Tale of Taming the Scheiber Beast: A Marine CAN Bus Adventure

## Prologue: Dreams of Smart Boats

Picture this: You're sitting on your boat, watching the sun set over the water. You reach for the light switch and think, "Wouldn't it be nice if I could automate all this?" Welcome to the world of modern boat automation, where the dream of a "smart boat" meets the reality of proprietary protocols that make you want to walk the plank.

This is the story of how one developer took on the Scheiber CAN bus system, armed with nothing but a Raspberry Pi, some CAN HATs, determination, and probably too much coffee.

## Chapter 1: Setting the Stage (November 27, 2025)

It started innocently enough. The hardware setup was actually the easy part. A Raspberry Pi with SSD storage (because SD cards and boats mix about as well as cats and water), a Waveshare 2CH CAN HAT to listen to two buses simultaneously, and a SailorHAT acting as a UPS for when the power inevitably goes out. One CAN interface for SeatalkNG, the other for Scheiber lighting control.

The initial commit landed on November 27th: "Initial version." Those two words carry the weight of naïve optimism. Little did our hero know that this would become a multi-week journey through the undocumented wilderness of proprietary CAN protocols.

## Chapter 2: The Golden Path and The Dark Woods (Early December)

SeatalkNG was the good kid. It followed NMEA2K standards, played nice with SignalK, and decoded beautifully. Within hours, navigation data was flowing like champagne at a boat christening.

Then there was Scheiber.

The Scheiber bus was... different. Messages rolled in, cryptic and inscrutable. No NMEA2K patterns. No documentation. Just hex dumps that might as well have been ancient hieroglyphics. The commits tell the tale:

- December 1st: "added can-utils" (The investigation begins)
- December 2nd: "added analyser" (Let's see what we're dealing with)
- December 2nd, 1:33 AM: "added can-naming support" (Trying to make sense of the chaos)

## Chapter 3: The Night of Discovery (December 3rd)

This is where things get interesting. Our developer is clearly burning the midnight oil, pushing commits at 2:31 AM, 2:39 AM, 3:18 AM. You can almost feel the excitement building:

- 2:31 AM: "it's actually blinking!" 

Imagine the scene: darkness outside, the only light coming from the screen and a boat light that's FINALLY responding to commands. Victory tastes sweet at 2:31 in the morning. The commit messages get almost giddy:

- 2:39 AM: "better convenience ;)" (The winky face says it all)
- 3:18 AM: "more insights"
- 5:00 AM: "we can switch stuff on and off!"

Sleep is for the weak. We've got lights to control!

## Chapter 4: The Architecture Emerges (December 3-4)

After the initial euphoria wore off, reality set in. Hacking together commands that make lights blink is one thing. Building a proper integration is another. The commits shift from experimentation to engineering:

- "refactoring"
- "first listener"  
- "first version with mqtt-bridge"

The MQTT bridge was born on December 3rd at 9:26 PM. This was the key that would unlock Home Assistant integration. But of course, nothing is ever that simple.

## Chapter 5: The Pattern Emerges (December 4-5)

By December 4th, patterns started revealing themselves from the noise. The commit log shows systematic reverse engineering in action:

- "use address & mask in PATTERNS"
- "publish properties"
- "dimming" (Oh yes, we're getting fancy now)

The developer discovered that Scheiber organizes switches in pairs. S1 & S2 share a status message (0x02160600), S3 & S4 another (0x02180600), and S5 & S6 yet another (0x021A0600). Each message carries both the ON/OFF state AND brightness level. It's almost elegant, once you understand it.

The device_types.yaml file was born on December 4th, transforming ad-hoc code into a proper configuration-driven system. This was the moment the project grew up.

## Chapter 6: The 1.0.0 Summit (December 5th)

Version 1.0.0 landed at 2:53 AM on December 5th: "Production release with MQTT improvements."

The developer had successfully:
- Decoded the Scheiber protocol
- Built a proper MQTT bridge
- Implemented Home Assistant auto-discovery
- Added brightness control
- Created a maintainable architecture

But this isn't a story about reaching the summit. It's a story about discovering that the summit was just base camp.

## Chapter 7: The Refactoring Wars (December 5-6)

With the basics working, the code smelled like... well, code that was written at 3 AM. Time for some serious refactoring:

- "Refactor: Reorganize file structure and extract CAN decoder"
- "Add project tooling: pyproject.toml with Poe task runner"
- "Add .gitignore and implement unit tests"

Professional developers know: If it doesn't have tests, it doesn't work. If it doesn't have proper structure, future-you will curse present-you.

## Chapter 8: The Availability Saga (December 6-7)

Here's where things got philosophical. When is a device "online"? This seemingly simple question spawned an entire arc:

- December 7th, 12:45 AM: "feat!: implement heartbeat-based availability for Bloc9"
- 1:36 AM: "Fix brightness control by preventing duplicate ON commands"  
- 2:47 AM: "Add optimistic MQTT state updates and fix availability recovery"

The problem was subtle: devices would go offline in Home Assistant even though they were actively talking on the CAN bus. Why? Because they were sending the same status repeatedly. If nothing changed, the code skipped the update. If updates were skipped for 60 seconds, the device was marked offline.

The fix? Update the heartbeat before checking if the message changed, not after. Sometimes the smallest bugs require the biggest detective work.

## Chapter 9: The Production Reality (December 7th)

Version 3.0.0 arrived with a breaking change: "Explicit entity configuration with safety controls." 

This wasn't just a technical decision. This was wisdom earned from real-world use. You don't want Home Assistant accidentally controlling your boat's underwater lights when you're trying to turn on the reading lamp. Some outputs needed to be switches. Others needed to be lights. Some needed explicit configuration to prevent "helpful" automation from doing unhelpful things.

The commit log shows rapid iteration throughout December 7th:
- 11:48 AM: "feat: add config integrity checks"
- 12:24 PM: "feat: add debug logging and cleanup old discovery topics"  
- 1:56 PM: "Add hierarchical device structure with via_device support"
- 4:30 PM: "Aft Beam Light and Under Water Light are high power devices and likely should not be dimmed"

Real-world testing reveals real-world problems. High-power lights don't dim nicely through a Bloc9 - they need relays. Better make them switches, not dimmable lights.

## Epilogue: The Never-Ending Story (December 7th, 8:13 PM)

The final commit of our tale: "fix: prevent devices from going offline when state is unchanged."

Version 3.1.6 shipped with a solution to the availability problem that had plagued the system. But notice something? This isn't "version 4.0 - Complete and Perfect Forever." This is 3.1.6 - a patch on a minor release of a major version.

Because here's the truth about reverse engineering proprietary protocols: You're never really done. There's always one more edge case, one more strange behavior when the voltage drops, one more scenario where the Bloc9 does something unexpected.

## Lessons Learned

Looking back at the 125+ commits over just 10 days:

1. **Start with the hardware right.** The SailorHAT UPS and dual CAN interfaces were wise choices from day one.

2. **Celebrate small victories.** That 2:31 AM "it's actually blinking!" was worth celebrating.

3. **Refactor early, refactor often.** The code at commit 50 was probably working. The code at commit 100 was maintainable.

4. **Real-world testing is the only testing that matters.** All the unit tests in the world won't tell you that high-power lights need different handling than reading lamps.

5. **Documentation is a love letter to future you.** Those detailed commit messages and the copilot-instructions.md file will save hours of head-scratching later.

6. **The best code is boring code.** By version 3.x, the exciting discovery phase was over. Now it's about stability, configuration management, and handling edge cases. That's when you know you've succeeded.

## The Future

The boat's lights now respond to Home Assistant automations. Sunset triggers gentle lighting changes. Presence detection knows when crew is aboard. The underwater lights can be scheduled. It's all there, running on a little Raspberry Pi, translating between the proprietary world of Scheiber and the open world of Home Assistant.

And somewhere, at 2:31 AM on some future night, a developer will push a commit: "it's actually working!" because they've just reverse engineered some other proprietary protocol on their boat.

The cycle continues. The smart boats get smarter. And the open-source community grows, one late-night commit at a time.

---

*Written with appreciation for the developer who turned 10 days of reverse engineering into 3.1.6 versions of working software. May your CAN buses always be stable, your MQTT brokers always available, and your coffee always strong.*
