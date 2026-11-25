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
      page.getByRole("heading", { name: "Conversations" }),
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
      page.getByRole("heading", { name: "Conversations" }),
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
