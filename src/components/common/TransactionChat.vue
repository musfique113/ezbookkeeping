<template>
    <button v-if="eligible" class="chat-launcher" type="button" @click="openChat">✦ AI chat</button>
    <dialog ref="dialog" class="transaction-chat" aria-labelledby="chat-title" @cancel="onCancel">
        <header>
            <div><strong id="chat-title">Transaction assistant</strong><small>Describe an expense, income, or transfer</small></div>
            <button type="button" aria-label="Close chat" :disabled="busy" @click="closeChat">×</button>
        </header>
        <p v-if="!enabled" class="notice">AI is not configured. Ask your administrator to enable AI text recognition and configure its provider.</p>
        <template v-else>
            <p class="notice">Chat text and your account/category names are sent to your configured AI provider. Nothing is saved without confirmation.</p>
            <div ref="history" class="chat-history" role="log" aria-live="polite" aria-label="Conversation">
                <p v-if="!messages.length">Try: “Yesterday I paid 850 BDT for groceries from bKash.” You can then correct details in another message.</p>
                <p v-for="(message, index) in messages" :key="index" :class="message.role">
                    <strong>{{ message.role === 'user' ? 'You' : 'Assistant' }}</strong><br>{{ message.content }}
                </p>
                <p v-if="busy" role="status">{{ saving ? 'Saving transaction…' : 'Thinking…' }}</p>
            </div>
            <section v-if="draft" class="draft" aria-label="Transaction preview">
                <strong>Review before saving</strong>
                <dl>
                    <dt>Type</dt><dd>{{ typeName }}</dd>
                    <dt>Amount</dt><dd>{{ amount(draft.sourceAmount) }} {{ sourceCurrency }}</dd>
                    <dt>Account</dt><dd>{{ accountName(draft.sourceAccountId) }}</dd>
                    <dt>Category</dt><dd>{{ categories.allTransactionCategoriesMap[draft.categoryId || '']?.name }}</dd>
                    <dt>Date / time</dt><dd>{{ draftTime }} ({{ timezone }})</dd>
                    <template v-if="draft.type === TransactionType.Transfer">
                        <dt>To account</dt><dd>{{ accountName(draft.destinationAccountId) }}</dd>
                        <dt>Received</dt><dd>{{ amount(draft.destinationAmount) }} {{ accounts.allAccountsMap[draft.destinationAccountId || '']?.currency }}</dd>
                    </template>
                    <dt>Note</dt><dd>{{ draft.comment || '—' }}</dd>
                </dl>
                <p>Check every field. Send any typed correction before confirming.</p>
                <button type="button" :disabled="busy || !!text.trim()" @click="save">Confirm and save transaction</button>
            </section>
            <p v-if="error" role="alert" class="chat-error">{{ error }}</p>
            <form @submit.prevent="send">
                <label for="transaction-chat-message">Message</label>
                <textarea id="transaction-chat-message" ref="input" v-model="text" maxlength="4000" rows="3" :disabled="busy || limitReached"
                          placeholder="Describe a transaction or answer a follow-up question…"></textarea>
                <div class="chat-actions">
                    <button type="button" :disabled="busy" @click="reset">New conversation</button>
                    <button type="submit" :disabled="busy || !text.trim() || limitReached">Send</button>
                </div>
                <small v-if="limitReached">Conversation limit reached. Start a new conversation.</small>
            </form>
        </template>
    </dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, useTemplateRef } from 'vue';
import { useAccountsStore } from '@/stores/account.ts';
import { useTransactionCategoriesStore } from '@/stores/transactionCategory.ts';
import { useTransactionsStore } from '@/stores/transaction.ts';
import { useUserStore } from '@/stores/user.ts';
import { Transaction } from '@/models/transaction.ts';
import type { RecognizedTransactionResponse, TransactionChatMessage } from '@/models/large_language_model.ts';
import { TransactionType } from '@/core/transaction.ts';
import { isUserLogined, isUserUnlocked } from '@/lib/userstate.ts';
import { isTransactionFromAITextRecognitionEnabled } from '@/lib/server_settings.ts';
import { getTimezoneOffsetMinutes } from '@/lib/datetime.ts';
import { getTimeZone } from '@/lib/settings.ts';
import { generateRandomUUID } from '@/lib/misc.ts';
import services from '@/lib/services.ts';

const accounts = useAccountsStore();
const categories = useTransactionCategoriesStore();
const transactions = useTransactionsStore();
const user = useUserStore();
const dialog = useTemplateRef<HTMLDialogElement>('dialog');
const input = useTemplateRef<HTMLTextAreaElement>('input');
const history = useTemplateRef<HTMLDivElement>('history');
const eligible = ref(false);
const messages = ref<TransactionChatMessage[]>([]);
const draft = ref<RecognizedTransactionResponse>();
const text = ref('');
const error = ref('');
const busy = ref(false);
const saving = ref(false);
let sessionId = generateRandomUUID();
let generation = 0;
let identity = '';
let timer: ReturnType<typeof setInterval>;
const enabled = computed(() => isTransactionFromAITextRecognitionEnabled());
const limitReached = computed(() => messages.value.length >= 18);
const timezone = computed(() => getTimeZone() || Intl.DateTimeFormat().resolvedOptions().timeZone);
const typeName = computed(() => draft.value?.type === TransactionType.Income ? 'Income' : draft.value?.type === TransactionType.Transfer ? 'Transfer' : 'Expense');
const sourceCurrency = computed(() => accounts.allAccountsMap[draft.value?.sourceAccountId || '']?.currency);
const draftTime = computed(() => draft.value?.time ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium', timeZone: timezone.value }).format(new Date(draft.value.time * 1000)) : '');
function amount(value?: number): string { return ((value || 0) / 100).toFixed(2); }
function accountName(id?: string): string { return accounts.allAccountsMap[id || '']?.name || ''; }
function reset(): void {
    generation++;
    messages.value = []; draft.value = undefined; text.value = ''; error.value = '';
    sessionId = generateRandomUUID();
}
function syncEligibility(): void {
    const allowed = !!user.currentUserBasicInfo && isUserLogined() && isUserUnlocked();
    const nextIdentity = allowed ? user.currentUserBasicInfo!.username : '';
    if (identity !== nextIdentity || (!allowed && eligible.value)) { reset(); dialog.value?.close(); }
    identity = nextIdentity;
    eligible.value = allowed;
}
onMounted(() => { syncEligibility(); timer = setInterval(syncEligibility, 500); });
onUnmounted(() => { clearInterval(timer); generation++; });
async function openChat(): Promise<void> {
    syncEligibility();
    if (!eligible.value) { return; }
    dialog.value?.showModal();
    try { await Promise.all([accounts.loadAllAccounts({ force: false }), categories.loadAllCategories({ force: false })]); }
    catch { error.value = 'Could not load accounts and categories. Close and reopen chat to retry.'; }
    await nextTick(); input.value?.focus();
}
function closeChat(): void { dialog.value?.close(); }
function onCancel(event: Event): void { if (busy.value) { event.preventDefault(); } }
async function scroll(): Promise<void> { await nextTick(); if (history.value) { history.value.scrollTop = history.value.scrollHeight; } }
async function send(): Promise<void> {
    syncEligibility();
    if (busy.value || !text.value.trim() || limitReached.value || !isUserUnlocked()) { return; }
    const content = text.value.trim();
    if (messages.value.reduce((n, m) => n + new TextEncoder().encode(m.content).length, 0) + new TextEncoder().encode(content).length > 20000) { error.value = 'Conversation is too long. Start a new conversation.'; return; }
    const request = [...messages.value, { role: 'user' as const, content }];
    if (request.some(m => new TextEncoder().encode(m.content).length > 4000)) { error.value = 'Message is too long. Please shorten it.'; return; }
    const current = generation;
    busy.value = true; error.value = ''; draft.value = undefined;
    try {
        const response = await services.chatTransaction({ messages: request });
        syncEligibility();
        if (current !== generation || !isUserUnlocked()) { return; }
        if (!response.data.success || !response.data.result) { throw new Error('Unable to prepare transaction.'); }
        messages.value = [...request, { role: 'assistant', content: response.data.result.reply }];
        draft.value = response.data.result.draft;
        sessionId = generateRandomUUID(); text.value = '';
    } catch (e) { if (current === generation) { error.value = (e as Error).message || 'AI request failed. Please try again.'; } }
    finally { busy.value = false; await scroll(); }
}
async function save(): Promise<void> {
    syncEligibility();
    const d = draft.value;
    if (!d || busy.value || !isUserUnlocked() || !d.time || !d.categoryId || !d.sourceAccountId || !d.sourceAmount) { return; }
    const current = generation;
    busy.value = true; saving.value = true; error.value = '';
    try {
        const offset = getTimezoneOffsetMinutes(d.time, timezone.value);
        const transaction = Transaction.createNewTransaction(d.type, d.time, timezone.value, offset);
        transaction.setCategoryId(d.categoryId);
        transaction.sourceAccountId = d.sourceAccountId;
        transaction.sourceAmount = d.sourceAmount;
        transaction.destinationAccountId = d.destinationAccountId || '0';
        transaction.destinationAmount = d.destinationAmount || 0;
        transaction.comment = d.comment || '';
        transaction.tagIds = d.tagIds || [];
        await transactions.saveTransaction({ transaction, defaultCurrency: user.currentUserDefaultCurrency, isEdit: false, clientSessionId: sessionId });
        syncEligibility();
        if (current !== generation) { return; }
        reset(); messages.value = [{ role: 'user', content: 'Transaction confirmed.' }, { role: 'assistant', content: 'Transaction saved. Start a new conversation to add another.' }];
    } catch (e) { if (current === generation) { error.value = ((e as Error).message || 'Save failed.') + ' If the result is uncertain, check Transaction Details before creating another draft.'; } }
    finally { busy.value = false; saving.value = false; await scroll(); }
}
</script>

<style scoped>
.chat-launcher { position: fixed; right: 20px; bottom: 80px; z-index: 2000; background: #804719; color: white; border: 0; border-radius: 28px; padding: 14px 20px; box-shadow: 0 4px 20px #0003; cursor: pointer; font: inherit; }
.transaction-chat { position: fixed; inset: 0; margin: auto; width: min(540px, calc(100vw - 24px)); max-height: 90dvh; padding: 0; border: 1px solid #d3c4b6; border-radius: 18px; background: #fffaf5; color: #30271f; font: 15px/1.5 system-ui, sans-serif; overflow: auto; box-sizing: border-box; }
.transaction-chat::backdrop { background: #0006; }
.transaction-chat header { display: flex; justify-content: space-between; padding: 20px; border-bottom: 1px solid #d3c4b6; }
.transaction-chat small { display: block; font-size: 12px; }
.transaction-chat button { font: inherit; cursor: pointer; padding: 8px 14px; border: 1px solid #9b7655; border-radius: 8px; background: white; color: #513416; }
.transaction-chat button:disabled { opacity: .5; cursor: default; }
.notice { padding: 12px 20px; margin: 0; font-size: 12px; background: #efe5d8; }
.chat-history { max-height: 32dvh; overflow-y: auto; padding: 0 20px; }
.chat-history p { white-space: pre-wrap; overflow-wrap: anywhere; padding: 12px; border-radius: 10px; background: #efe9e1; }
.chat-history .user { margin-left: 30px; background: #f1d5bb; }
.draft { margin: 12px 20px; padding: 16px; border: 1px solid #b68151; border-radius: 12px; }
.draft dl { display: grid; grid-template-columns: 100px 1fr; gap: 6px; }
.draft dt { font-weight: 600; } .draft dd { margin: 0; overflow-wrap: anywhere; }
.chat-error { margin: 12px 20px; color: #a01d13; }
.transaction-chat form { padding: 16px 20px; }
.transaction-chat textarea { display: block; width: 100%; box-sizing: border-box; font: inherit; padding: 10px; background: white; color: #30271f; border: 1px solid #9b7655; border-radius: 8px; resize: vertical; }
.chat-actions { display: flex; justify-content: space-between; margin-top: 10px; gap: 10px; }
</style>
