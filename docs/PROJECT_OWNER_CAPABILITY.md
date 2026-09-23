# Anonymous project owner capability

Issue: #203

## Proč

MVP má být použitelné bez povinné registrace a bez placeného identity providera.
Zároveň klientský `owner_user_id` nesmí sloužit jako authorization.

Proto může anonymně uložený projekt používat samostatný owner capability token.

## Model

Při vytvoření projektu vznikne min. 256bit náhodný token.

- raw token se vrátí klientovi pouze jednou,
- server ukládá pouze domain-separated SHA-256 hash,
- token opravňuje jen ke správě konkrétního projektu,
- read-only share používá zcela jinou token domain,
- token lze rotovat nebo revokovat.

## Omezení

Ztráta owner capability u anonymního projektu znamená ztrátu možnosti projekt
spravovat, dokud není projekt navázán na budoucí účet/passkey.

Proto je capability vhodná pro zero-cost MVP, ne konečný recovery model.

## Budoucí account binding

Pozdější účet/passkey může převzít projekt po prokázání platného owner
capability. Poté lze capability rotovat nebo zrušit bez změny share linků.

## API

Domain/persistence je samostatná od transportu. Owner mutation endpoint smí
používat capability pouze server-side, ideálně přes
`Authorization: Bearer <owner-capability>`; raw token se nikdy neloguje.
