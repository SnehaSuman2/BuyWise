# BuyWise API on Oracle Cloud Always Free

Written for: whoever is doing the deploy, start to finish.

The API moves to an Oracle Always Free ARM instance. It never sleeps, so the
cold starts go away, and it costs nothing for as long as Oracle keeps the tier.
The frontend stays on Vercel and the database stays on Neon, so this machine
holds no data and can be thrown away and rebuilt at any point.

Budget an hour if Oracle cooperates. The one step that can stall you is ARM
capacity, covered below.

## What you need first

- An Oracle Cloud account. Signing up asks for a card for identity
  verification; the Always Free resources are not charged.
- Control of `buywise.co.in` DNS, to add an `api` subdomain.
- Your environment values. Take them from the Render dashboard.

## 1. Create the instance

In the Oracle console: **Compute > Instances > Create instance**.

- **Image**: Ubuntu 22.04 or 24.04.
- **Shape**: Change shape > **Ampere** > `VM.Standard.A1.Flex`. Set **2 OCPUs
  and 12 GB** of memory. That is the whole Always Free allowance since Oracle
  halved it in June 2026, and staying inside it is what keeps the bill at zero.
- **SSH keys**: upload your public key, or let Oracle generate one and download
  the private key before you leave the page. You cannot get it later.
- Leave networking on the defaults; it creates a VCN and gives a public IP.

**If it says "Out of capacity"**, that is Oracle, not you. ARM capacity in
popular regions is often exhausted. Options, in order of effort: try again
every few hours, try a different availability domain in the same region, or
create the account in a quieter region. Some people retry for days. If you are
against a deadline, this is the moment to reconsider.

## 2. Open the firewall, both of them

Oracle blocks traffic at two independent layers and you must open both. Missing
the second is the single most common reason a working server appears dead.

**The cloud layer**: Networking > Virtual Cloud Networks > your VCN > Security
Lists > the default list > Add Ingress Rules. Add two, both stateless off,
source `0.0.0.0/0`, IP protocol TCP:

| Destination port | For |
| --- | --- |
| 80 | HTTP, needed for the certificate challenge |
| 443 | HTTPS |

**The machine layer** is handled by the setup script in the next step.

## 3. Prepare the machine

    ssh ubuntu@<your-instance-ip>
    curl -fsSL https://raw.githubusercontent.com/SnehaSuman2/BuyWise/main/deploy/oracle/setup.sh | bash

That installs Docker, opens ports 80 and 443 in the machine's own iptables
rules, and clones the repository to `~/BuyWise`.

Log out and back in afterwards, so your user picks up its Docker group.

## 4. Point the domain at it

Add a DNS record wherever `buywise.co.in` is managed:

| Type | Name | Value |
| --- | --- | --- |
| A | api | your instance's public IP |

Wait until `dig +short api.buywise.co.in` returns that IP. Caddy cannot get a
certificate before the name resolves, and a failed attempt is rate-limited by
Let's Encrypt, so it is worth checking rather than guessing.

## 5. Write the environment

    nano ~/BuyWise/.env

Copy every variable from Render. Three differ from what Render has:

    ENVIRONMENT=production
    API_DOMAIN=api.buywise.co.in
    API_PUBLIC_URL=https://api.buywise.co.in
    CORS_ORIGINS=https://www.buywise.co.in,https://buywise.co.in

`API_PUBLIC_URL` matters for photo search: an uploaded image is served from
that address for Google Lens to fetch.

Keep `DATABASE_URL` and `DIRECT_DATABASE_URL` pointing at Neon. Nothing is
migrated, so there is nothing to lose and rollback stays trivial.

## 6. Start it

    cd ~/BuyWise
    docker compose -f deploy/oracle/docker-compose.yml up -d --build

The first build takes a few minutes on ARM. Watch it, including the
certificate:

    docker compose -f deploy/oracle/docker-compose.yml logs -f

## 7. Check before switching anything

    curl https://api.buywise.co.in/health
    curl https://api.buywise.co.in/api/v1/meta

`meta` should say `data_mode: live` and name your search and AI providers. Then
try a real search:

    curl -X POST https://api.buywise.co.in/api/v1/search \
      -H 'Content-Type: application/json' \
      -d '{"query":"sony wh-1000xm5","page_size":5}'

## 8. Point the site at it

Only now. In Vercel, set `NEXT_PUBLIC_API_URL` to `https://api.buywise.co.in`
and redeploy: that prefix is compiled into the build, so it does not take
effect until a rebuild.

Then:

- Add `https://api.buywise.co.in` to the Google OAuth client's authorised
  origins.
- Update the Razorpay webhook URL.
- Update `API_URL` in the GitHub repository secrets so scheduled jobs arrive
  here.
- Leave Render running for a day. Rollback is changing that one Vercel
  variable back and redeploying.

## Afterwards

- The keep-warm workflow can be deleted; nothing sleeps now.
- `docker compose ... logs -f api` is where application logs go.
- To deploy a change: `git -C ~/BuyWise pull && docker compose -f
  deploy/oracle/docker-compose.yml up -d --build`.
- Oracle reclaims idle Always Free instances. This one serves traffic, so it
  should be safe, but do not leave it doing nothing for weeks.

## Moving the database here later

Not needed now, and not recommended before a demo. When you do want it, the
machine has room: add a Postgres service to the compose file, dump from Neon
with `pg_dump`, restore, and change `DATABASE_URL`. Take a backup strategy
seriously first, because at that point this machine holds data that matters.
