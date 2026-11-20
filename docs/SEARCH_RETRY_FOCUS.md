# Search retry keyboard focus (#400)

On a failed search the results remain hidden. A keyboard-initiated retry keeps focus on a visibly busy, `aria-disabled` retry control while the same intent is requested again; repeated activation cannot issue a second request. A second failure restores focus to Retry. A successful request hands focus to the results heading or, for an empty result/index, its next-action link. If the user moves focus to another connected control while waiting, the response does not steal it.

This is a bounded accessibility follow-up, not a claim that all #400 acceptance criteria or current official-source data have been audited. The full-stack regression uses the real local D1/API for recovery, intercepting only the outage/delay; it also covers mobile focus choice, axe and reflow. No API facts, eligibility or financial estimates are inferred from an outage.
