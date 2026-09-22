# Deploying the BuyWise API to Heroku

Written for: whoever is doing the deploy, following along step by step.

Why Heroku: the GitHub Student Developer Pack gives $13 of Heroku credit a month
for 24 months. A Basic dyno costs $7 a month and never sleeps, which removes the
cold starts the Render free tier has. The credit covers it with room to spare.

The database stays on Neon. Nothing is migrated, so there is nothing to lose.

## Before you start

- Claim the Heroku offer at https://www.heroku.com/github-students/ and wait for
  the credit to appear on the account.
- Install the CLI: `brew install heroku/brew/heroku` (macOS).
- Have the values from Render's environment ready. You are copying them, not
  changing them.

## 1. Create the app

    heroku login
    heroku create buywise-api --stack container

Note the URL it prints, for example `https://buywise-api-1234.herokuapp.com`.

## 2. Copy the environment across

Every variable currently set on Render must be set here. From the repository root:

    heroku config:set -a buywise-api \
      ENVIRONMENT=production \
      DATABASE_URL='<the Neon pooled URL from Render>' \
      DIRECT_DATABASE_URL='<the Neon direct URL from Render>' \
      SECRET_KEY='<the same value as Render>' \
      SERPAPI_API_KEY='<...>' \
      GEMINI_API_KEY='<...>' \
      OPENAI_API_KEY='<your Groq key>' \
      OPENAI_BASE_URL='https://api.groq.com/openai/v1' \
      OPENAI_MODEL='openai/gpt-oss-20b' \
      GOOGLE_CLIENT_ID='<...>' \
      GOOGLE_CLIENT_SECRET='<...>' \
      RAZORPAY_KEY_ID='<...>' \
      RAZORPAY_KEY_SECRET='<...>' \
      EMAIL_API_KEY='<...>' \
      ADMIN_EMAILS='<your email>' \
      CRON_SECRET='<...>' \
      NEXT_PUBLIC_APP_URL='https://www.buywise.co.in' \
      CORS_ORIGINS='https://www.buywise.co.in,https://buywise.co.in'

Then set the app's own public URL, using the hostname Heroku gave you:

    heroku config:set -a buywise-api API_PUBLIC_URL='https://buywise-api-1234.herokuapp.com'

`API_PUBLIC_URL` matters: photo search uploads an image and Google Lens has to be
able to fetch it from that address.

## 3. Use a dyno that does not sleep

    heroku ps:type -a buywise-api web=basic

Eco dynos sleep after 30 minutes idle, which is the problem we are leaving behind.
Basic does not.

## 4. Deploy

The backend lives in a subdirectory, so push just that directory as the app root:

    git remote add heroku https://git.heroku.com/buywise-api.git
    git subtree push --prefix backend heroku main

Watch it build. Migrations run on boot, and because the database is the same Neon
one Render already migrated, there will be nothing to apply.

## 5. Check it before switching anything

    curl https://buywise-api-1234.herokuapp.com/health
    curl https://buywise-api-1234.herokuapp.com/api/v1/meta

`meta` should report `data_mode: live` and the search and AI providers you set.

## 6. Point the site at it

In Vercel, set `NEXT_PUBLIC_API_URL` to the Heroku URL and redeploy. That prefix
is compiled into the build, so a redeploy is required for it to take effect.

Then add the Heroku URL to Google OAuth's authorised origins if you sign in with
Google, and update the Razorpay webhook URL.

## 7. Afterwards

- Keep Render running for a day in case you want to switch back; pointing
  `NEXT_PUBLIC_API_URL` at the old URL and redeploying is the whole rollback.
- Update `API_URL` in the GitHub repository secrets so scheduled jobs hit Heroku.
- The keep-warm workflow can be deleted once nothing sleeps.

## Costs

| Item | Cost | Covered by the $13 student credit |
| --- | --- | --- |
| Basic dyno, always on | $7/month | yes |
| Neon database (unchanged) | free tier | not billed by Heroku |

Leaving about $6 a month spare, for 24 months.
