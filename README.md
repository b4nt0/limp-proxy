# LLM to Instant Messaging proxy (LIMP)

This project makes it easy to expose an LLM equipped with tools that connect to external systems through instant messaging programs like Slack or Microsoft Teams.

## Use case

Expose your system as an instant messaging (IM) bot in a multi-tenant environment.

Your system is defined as an OAuth2 authentication endpoint + a number of tools that are exposed to LIMP in the form of an OpenAPI specification.

Users would install a bot powered by LIMP in their instant messaging environment. Once a user sends the first message to the bot, it would prompt the user to authenticate with the target system.

Once the authentication is complete, the user would continue interacting with the instant messaging bot in DMs, channels, or through bot commands to get information from your system or execute actions in your system.

## Architecture

LIMP consists of:

- Bot server
  - Optional admin interface:
    - Works only if enabled in the configuration file
    - Requires simple authentication as defined in the configuration file
    - Provides a visual editor for the configuration file values
  - Instant messaging API:
    - Handle instant messaging requests
  - OAuth2 service pages
    - Handle the start of OAuth2 authorization flow
    - Handle the end of the OAuth2 authorization flow (success or failure)
- Relational SQL database to store:
  - External chat users data
  - Authorization data:
    - OAuth2 tokens for external systems
    - OAuth2 authorization state
  - Conversation context and history per user
- Configuration file
  - Bot application identifiers
  - External systems and tools definitions
    - OpenAPI specs of the tools
    - OAuth2 URLs, identifiers, and secrets
  - Prompts and context files
  - External LLM URLs and credentials

The bot server is implemented with Python FastAPI.
The communication with the external database is done with SQLAlchemy.

### Technical requirements

The database is either a built-in SQLite or an external Postgresql database. Other database engines are possible, but not officially supported.

The LLM is only OpenAI ChatGPT. 

Authorization is only OAuth2.

External tools are only in OpenAPI format.

Instant messaging frontends are Slack and Microsoft Teams.

The configuration file format is YAML.

## Workflows

### Prerequisites

- The bot applications have to be registered at target instant messaging platforms
- OAuth2 client, secret, and callback URLs are set in the target systems

### Bot installation

A user of an IM installs the LIMP bot in their system. 

### Bot message

1. A user of an IM sends a DM to the LIMP bot. 

2. LIMP looks for prior context of the conversation, and attaches it if necessary.

3. LIMP optionally checks for the user's authorization to use the bot.

4. LIMP sends the user's request + tools to the LLM.

5. If LLM returns a response without tool calls, skip to step 15

6. LIMP checks if that user has authorization in the target system where the tool is invoked from.

7. If yes, it proceed to step 12

8. Send the user the authorization link or a button that leads to a "start authorization" page

9. Once authorization is initiated, generate and save a state, and make an authorization request to a target system

10. Respond to the user that authorization is ongoing 

11. Once authorization has been granted, continue working

12. Call the tool in the target system

13. If the tool call succeeded, add the results to the conversation

14. Check if the number of iterations exceeded a configured value, if so abort the cycle. Otherwise go to 4.

15. Render the output to the user

## Error handling

### User space

These errors are not necessarily user errors, they are errors where the user is affected.

#### Principle 1. Always a human answer to user's request

For example:

- If an authorization error occurred, explain to the user what happened and what they can do

- If an interaction with the tool yielded an error, still attempt to continue interacting with the LLM to handle the absent data or try another tool

- If the number of iterations exceeded the maximum allowed without convergence, still attempt one last iteration that asks the LLM to deliver the interim or partial results

- If there was an LLM communication error, respond with a configured (with a fall back to a hard-coded) message explaining what happened.

#### Principle 2. Always log what happened

In case of user errors, they are logged to the standard logger with the `error` log level.

### Admin errors

#### Interactive admin errors are uncaught

When admin is likely operating the software, e.g. when LIMP starts up and detects a configuration file issue, the errors are uncaught.

#### Unattended admin errors are logged, recovered, and alerts are raised

When admin is likely not operating the system:

- The errors are logged with the `error` log level, and an `admin` tag.

- A reasonable attempt at recovery is made, for example if a database failed to connect, a reconnect attempt is made.

- An alert is raised if configured in the file. The alerts are raised by calling an external POST API.

- If a user is affected, they recieve a configured (with a fall back to hard-coded) message explaning what happened.