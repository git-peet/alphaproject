import { expect, test } from "@playwright/test"
import { createUser } from "./utils/privateApi"
import {
  randomEmail,
  randomItemDescription,
  randomPassword,
} from "./utils/random"
import { logInUser } from "./utils/user"

const TRANSCRIPT_MAX_LENGTH = 20_000

const randomConversationTitle = () =>
  `Conversation ${Math.random().toString(36).substring(7)}`

test.describe("Conversations", () => {
  test.use({ storageState: { cookies: [], origins: [] } })
  let email: string
  const password = randomPassword()

  test.beforeAll(async () => {
    email = randomEmail()
    await createUser({ email, password })
  })

  test.beforeEach(async ({ page }) => {
    await logInUser(page, email, password)
    await page.goto("/conversations")
  })

  test("Conversations page is accessible and shows empty state", async ({
    page,
  }) => {
    await expect(
      page.getByRole("heading", { name: "Conversations", exact: true }),
    ).toBeVisible()
    await expect(
      page.getByText("You don't have any conversations yet"),
    ).toBeVisible()
  })

  test("Create a conversation with a transcript", async ({ page }) => {
    const title = randomConversationTitle()
    const transcript = randomItemDescription()

    await page.getByRole("button", { name: "Add Conversation" }).click()
    await page.getByLabel("Title").fill(title)
    await page.getByLabel("Transcript").fill(transcript)
    await page.getByRole("button", { name: "Save" }).click()

    await expect(
      page.getByText("Conversation created successfully"),
    ).toBeVisible()
    await expect(page.getByText(title)).toBeVisible()
  })

  test("Title and transcript are required", async ({ page }) => {
    await page.getByRole("button", { name: "Add Conversation" }).click()
    await page.getByLabel("Title").fill("")
    await page.getByLabel("Title").blur()

    await expect(page.getByText("Title is required")).toBeVisible()

    await page.getByLabel("Transcript").fill("")
    await page.getByLabel("Transcript").blur()

    await expect(page.getByText("Transcript is required")).toBeVisible()
  })

  test("Transcript over the limit is rejected before submission", async ({
    page,
  }) => {
    await page.getByRole("button", { name: "Add Conversation" }).click()
    await page.getByLabel("Title").fill(randomConversationTitle())
    await page
      .getByLabel("Transcript")
      .fill("x".repeat(TRANSCRIPT_MAX_LENGTH + 1))
    await page.getByLabel("Transcript").blur()

    await expect(page.getByText("Transcript is too long")).toBeVisible()
  })

  test("Open a conversation and run triage", async ({ page }) => {
    const title = randomConversationTitle()

    await page.getByRole("button", { name: "Add Conversation" }).click()
    await page.getByLabel("Title").fill(title)
    await page.getByLabel("Transcript").fill("Customer asks about an invoice")
    await page.getByRole("button", { name: "Save" }).click()
    await expect(
      page.getByText("Conversation created successfully"),
    ).toBeVisible()

    await page.getByRole("link", { name: `Open ${title}` }).click()
    await expect(page.getByRole("heading", { name: title })).toBeVisible()
    await expect(page.getByText("Customer asks about an invoice")).toBeVisible()
    await expect(
      page.getByText("No triage yet. Run triage", { exact: false }),
    ).toBeVisible()

    await page.getByRole("button", { name: "Run triage" }).click()

    await expect(page.getByText("Triage completed")).toBeVisible()
    await expect(page.getByText("Fake triage summary")).toBeVisible()
    await expect(page.getByText("general", { exact: true })).toBeVisible()
    await expect(page.getByText("neutral", { exact: true })).toBeVisible()
    await expect(
      page.getByText("Review the conversation", { exact: true }),
    ).toBeVisible()

    await page.reload()
    await expect(page.getByText("Fake triage summary")).toBeVisible()
  })

  test("Delete a conversation", async ({ page }) => {
    const title = randomConversationTitle()

    await page.getByRole("button", { name: "Add Conversation" }).click()
    await page.getByLabel("Title").fill(title)
    await page.getByLabel("Transcript").fill("Short transcript")
    await page.getByRole("button", { name: "Save" }).click()
    await expect(page.getByText(title)).toBeVisible()

    await page.getByRole("link", { name: `Open ${title}` }).click()
    await page.getByRole("button", { name: "Delete Conversation" }).click()
    await page.getByRole("button", { name: "Delete", exact: true }).click()

    await expect(
      page.getByText("The conversation was deleted successfully"),
    ).toBeVisible()
    await expect(
      page.getByRole("heading", { name: "Conversations", exact: true }),
    ).toBeVisible()
    await expect(page.getByText(title)).not.toBeVisible()
  })
})

test.describe("Conversation privacy", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Another user's conversation is not exposed", async ({
    page,
    browser,
  }) => {
    const ownerEmail = randomEmail()
    const otherEmail = randomEmail()
    const ownerPassword = randomPassword()
    const otherPassword = randomPassword()
    await createUser({ email: ownerEmail, password: ownerPassword })
    await createUser({ email: otherEmail, password: otherPassword })

    await logInUser(page, ownerEmail, ownerPassword)
    await page.goto("/conversations")

    const title = randomConversationTitle()
    await page.getByRole("button", { name: "Add Conversation" }).click()
    await page.getByLabel("Title").fill(title)
    await page.getByLabel("Transcript").fill("Private owner transcript")
    await page.getByRole("button", { name: "Save" }).click()
    await page.getByRole("link", { name: `Open ${title}` }).click()
    await expect(page.getByRole("heading", { name: title })).toBeVisible()

    const conversationUrl = page.url()

    const otherContext = await browser.newContext()
    const otherPage = await otherContext.newPage()
    await logInUser(otherPage, otherEmail, otherPassword)
    await otherPage.goto(conversationUrl)

    // The template logs out on 403, so the other user never sees the content.
    await otherPage.waitForURL(/\/login$/)
    await expect(otherPage.getByText(title)).not.toBeVisible()
    await expect(
      otherPage.getByText("Private owner transcript"),
    ).not.toBeVisible()

    await otherContext.close()
  })
})

test.describe("Conversation search and pagination", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  const apiBase = () => process.env.VITE_API_URL ?? ""

  const seedConversations = async (
    request: import("@playwright/test").APIRequestContext,
    email: string,
    password: string,
    titles: string[],
  ) => {
    const tokenResponse = await request.post(
      `${apiBase()}/api/v1/login/access-token`,
      { form: { username: email, password } },
    )
    expect(tokenResponse.ok()).toBeTruthy()
    const { access_token } = await tokenResponse.json()

    for (const title of titles) {
      const created = await request.post(`${apiBase()}/api/v1/conversations/`, {
        headers: { Authorization: `Bearer ${access_token}` },
        data: { title, transcript: "Seeded transcript" },
      })
      expect(created.ok()).toBeTruthy()
    }
  }

  test("Search narrows the list and shows a no-match state", async ({
    page,
    request,
  }) => {
    const email = randomEmail()
    const password = randomPassword()
    await createUser({ email, password })
    await seedConversations(request, email, password, [
      "Invoice alpha",
      "Invoice beta",
      "Shipping question",
    ])
    await logInUser(page, email, password)
    await page.goto("/conversations")

    await page.getByLabel("Search conversations").fill("INVOICE")
    await page.getByRole("button", { name: "Search" }).click()

    await expect(page.getByText("Invoice alpha")).toBeVisible()
    await expect(page.getByText("Invoice beta")).toBeVisible()
    await expect(page.getByText("Shipping question")).not.toBeVisible()
    await expect(
      page.getByText("Showing 1 to 2 of 2 conversations"),
    ).toBeVisible()

    await page.getByLabel("Search conversations").fill("zzz no match")
    await page.getByRole("button", { name: "Search" }).click()

    await expect(
      page.getByText("No conversations match your search"),
    ).toBeVisible()
    await expect(page.getByText("Invoice alpha")).not.toBeVisible()
  })

  test("Clearing search restores the full list", async ({ page, request }) => {
    const email = randomEmail()
    const password = randomPassword()
    await createUser({ email, password })
    await seedConversations(request, email, password, [
      "Kept by clear",
      "Other subject",
    ])
    await logInUser(page, email, password)
    await page.goto("/conversations")

    await page.getByLabel("Search conversations").fill("kept")
    await page.getByRole("button", { name: "Search" }).click()
    await expect(page.getByText("Other subject")).not.toBeVisible()

    await page.getByRole("button", { name: "Clear" }).click()

    await expect(page.getByText("Kept by clear")).toBeVisible()
    await expect(page.getByText("Other subject")).toBeVisible()
    await expect(
      page.getByText("Showing 1 to 2 of 2 conversations"),
    ).toBeVisible()
  })

  test("Pagination moves to the next page and resets on a new search", async ({
    page,
    request,
  }) => {
    const email = randomEmail()
    const password = randomPassword()
    await createUser({ email, password })
    const titles = Array.from(
      { length: 12 },
      (_, index) => `Bulk item ${index}`,
    )
    await seedConversations(request, email, password, titles)
    await logInUser(page, email, password)
    await page.goto("/conversations")

    await expect(
      page.getByText("Showing 1 to 10 of 12 conversations"),
    ).toBeVisible()
    await expect(page.getByRole("button", { name: "Previous" })).toBeDisabled()

    await page.getByRole("button", { name: "Next" }).click()

    await expect(
      page.getByText("Showing 11 to 12 of 12 conversations"),
    ).toBeVisible()
    await expect(page.getByRole("button", { name: "Next" })).toBeDisabled()
    await expect(page.getByRole("button", { name: "Previous" })).toBeEnabled()

    await page.getByRole("button", { name: "Previous" }).click()
    await expect(
      page.getByText("Showing 1 to 10 of 12 conversations"),
    ).toBeVisible()

    await page.getByRole("button", { name: "Next" }).click()
    await expect(
      page.getByText("Showing 11 to 12 of 12 conversations"),
    ).toBeVisible()

    await page.getByLabel("Search conversations").fill("Bulk item 11")
    await page.getByRole("button", { name: "Search" }).click()

    await expect(
      page.getByText("Showing 1 to 1 of 1 conversations"),
    ).toBeVisible()
    await expect(page.getByRole("button", { name: "Previous" })).toBeDisabled()
  })
})
