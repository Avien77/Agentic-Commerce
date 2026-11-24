# Red-flag knowledge base

Starter entries for the scam check (plan section 4, step 5). Keep the format exactly as below:
`## <ID> <title>`, then `severity`, `patterns` (comma-separated, lowercase), `why`, `source`.
Severity `high` sets r_text to 1.0, `medium` to 0.5 (config.yaml: risk.severity_score).

TODO before the data freeze: grow this to 30–40 entries written in your own words, and fill
in `source` with the link each entry is based on (scam-awareness posts, marketplace safety
pages, collector guides).

## RF-01 Payment before meeting
- severity: high
- patterns: zelle only, cash app only, cashapp only, venmo only, wire transfer, gift card, payment first, pay first, deposit, deposit to hold
- why: Asking for money before the buyer can see the card is the most common marketplace scam; these payment methods can't be reversed.
- source: TODO

## RF-02 Unprotected PayPal payment
- severity: high
- patterns: friends and family, friends & family, f&f, ff only, goods and services not accepted
- why: Friends and Family payments have no buyer protection, so the money is gone if the card never arrives.
- source: TODO

## RF-03 Fake or reproduction card
- severity: high
- patterns: proxy, proxies, custom card, custom, replica, orica, fan made, fanmade, art card, not original, unofficial
- why: The listing admits the card is not a genuine printing, so it has none of the real card's value.
- source: TODO

## RF-04 Shipping only, no meetup
- severity: medium
- patterns: shipping only, ships only, no meetups, no meetup, will ship after payment, ship after payment
- why: A local seller who refuses to meet makes it impossible to check the card before paying.
- source: TODO

## RF-05 Urgency pressure
- severity: medium
- patterns: need it gone today, need gone today, first come first serve, first come first served, lots of interest, many buyers, act fast, today only
- why: Pressure to decide fast is used to stop buyers from checking the card or the price.
- source: TODO

## RF-06 Stock or borrowed photos
- severity: medium
- patterns: stock photo, stock image, photo from google, pic from online, not my photo, not actual card
- why: Without photos of the actual card, the buyer can't judge its condition or whether it exists.
- source: TODO

## RF-07 Moving the deal off the platform
- severity: medium
- patterns: text me at, email me at, whatsapp, telegram, message me on, contact me off
- why: Moving the conversation elsewhere removes the platform's records and protections.
- source: TODO

## RF-08 Seller acting for someone else
- severity: medium
- patterns: on behalf of, for my cousin, my nephew's, out of the country, overseas, currently traveling
- why: A seller who can't meet or doesn't have the card in hand is a common setup for non-delivery.
- source: TODO

## RF-09 Refuses inspection
- severity: high
- patterns: no inspection, can't inspect, cannot inspect, no looking, as is no questions
- why: A genuine seller has no reason to stop a buyer from looking at the card before paying.
- source: TODO

## RF-10 Vague identity of the card
- severity: medium
- patterns: not sure which set, don't know the set, unknown set, might be 1st edition, could be first edition
- why: Uncertain identity on an expensive card often hides a cheaper printing or a fake.
- source: TODO
