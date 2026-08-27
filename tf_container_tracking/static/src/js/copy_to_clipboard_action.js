/** @odoo-module **/

import { registry } from "@web/core/registry";

async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return;
    }
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
}

registry.category("actions").add("tf_container_tracking.copy_to_clipboard", async (env, action) => {
    const params = action.params || {};
    const text = params.text || "";
    if (text) {
        await copyText(text);
    }
    env.services.notification.add(params.message || "Copied to clipboard.", {
        type: "success",
    });
});
