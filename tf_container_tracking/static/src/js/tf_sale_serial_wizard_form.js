/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

patch(FormController.prototype, {
    async beforeExecuteActionButton(clickParams) {
        if (this.props.resModel === "tf.sale.serial.wizard") {
            const activeEl = this.ui.activeElement || document.activeElement;
            if (activeEl && typeof activeEl.blur === "function") {
                activeEl.blur();
                await Promise.resolve();
            }
            const assignList = this.model.root?.data?.assign_line_ids;
            if (assignList?.leaveEditMode) {
                await assignList.leaveEditMode({ canAbandon: false });
            }
            const lineList = this.model.root?.data?.line_ids;
            if (lineList?.leaveEditMode) {
                await lineList.leaveEditMode({ canAbandon: false });
            }
        }
        return super.beforeExecuteActionButton(...arguments);
    },
});
