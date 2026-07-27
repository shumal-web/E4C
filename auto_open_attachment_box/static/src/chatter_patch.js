import { Chatter } from "@mail/chatter/web_portal/chatter";
import { patch } from "@web/core/utils/patch";
import { useEffect } from "@odoo/owl";

Chatter.defaultProps.isAttachmentBoxVisibleInitially = true;

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        useEffect(
            () => {
                if (this.state.thread && !this.state.thread.isLoadingAttachments) {
                    if (this.attachments.length > 0) {
                        this.state.isAttachmentBoxOpened = true;
                    }
                }
            },
            () => [this.state.thread, this.state.thread?.isLoadingAttachments, this.attachments.length]
        );
    },
});
