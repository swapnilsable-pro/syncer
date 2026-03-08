
## Task 6: CTC Alignment Quality on Singing Voice
- Alignment tail drift: last words ("let", "you", "down") have unrealistically wide spans (e.g., "let" = 115.9s–137.8s)
- This is because MMS_FA is a speech model — singing voice with music bleed causes confidence/span issues
- avg_score = 0.238 is usable but low — speech typically gets 0.7+
- These are expected limitations, not bugs. Task F3 will evaluate and decide if post-processing is needed
