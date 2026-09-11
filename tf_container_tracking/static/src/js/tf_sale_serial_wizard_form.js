/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { onMounted, onWillUnmount } from "@odoo/owl";

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.tfSaleSerialDialog = null;
        this.tfContainerSerialDialog = null;
        onMounted(() => {
            if (this.props.resModel === "tf.sale.serial.wizard") {
                this.rootRef.el?.classList.add("tf_sale_serial_wizard");
                this.tfSaleSerialDialog = this.rootRef.el?.closest(".modal-dialog");
                this.tfSaleSerialDialog?.classList.add("tf_sale_serial_dialog");
            }
            if (this.props.archInfo?.xmlDoc?.getAttribute("class") === "tf_sale_serial_container_wizard") {
                this.rootRef.el?.classList.add("tf_sale_serial_container_wizard");
                this.tfContainerSerialDialog = this.rootRef.el?.closest(".modal-dialog");
                this.tfContainerSerialDialog?.classList.add("tf_sale_serial_container_dialog");
            }
        });
        onWillUnmount(() => {
            this.tfSaleSerialDialog?.classList.remove("tf_sale_serial_dialog");
            this.tfContainerSerialDialog?.classList.remove("tf_sale_serial_container_dialog");
        });
    },

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
