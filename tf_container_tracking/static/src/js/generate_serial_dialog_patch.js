/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { onMounted, onWillStart, useRef } from "@odoo/owl";
import { x2ManyCommands } from "@web/core/orm_service";
import { getId } from "@web/model/relational_model/utils";
import { parseInteger } from "@web/views/fields/parsers";
import { GenerateDialog } from "@stock/widgets/generate_serial";

patch(GenerateDialog.prototype, {
    setup() {
        super.setup(...arguments);
        this.tfLength = useRef("tfLength");
        this.tfWidth = useRef("tfWidth");
        this.tfHeight = useRef("tfHeight");
        this.tfDimensionUnit = useRef("tfDimensionUnit");
        this.tfWeight = useRef("tfWeight");
        this.tfWeightUnit = useRef("tfWeightUnit");
        this.tfDefaults = {};

        onWillStart(async () => {
            if (!this.props.move?.data?.id || this.props.mode !== "generate") {
                return;
            }
            this.tfDefaults = await this.orm.call(
                "stock.move",
                "tf_get_generate_serial_dialog_defaults",
                [[this.props.move.data.id]]
            );
        });

        onMounted(() => {
            if (this.props.mode !== "generate") {
                return;
            }
            if (this.tfDefaults.first_serial && this.nextSerial.el && !this.nextSerial.el.value) {
                this.nextSerial.el.value = this.tfDefaults.first_serial;
            }
            if (this.tfLength.el) {
                this.tfLength.el.value = this.tfDefaults.tf_length || 0;
            }
            if (this.tfWidth.el) {
                this.tfWidth.el.value = this.tfDefaults.tf_width || 0;
            }
            if (this.tfHeight.el) {
                this.tfHeight.el.value = this.tfDefaults.tf_height || 0;
            }
            if (this.tfDimensionUnit.el && this.tfDefaults.tf_dimension_unit) {
                this.tfDimensionUnit.el.value = this.tfDefaults.tf_dimension_unit;
            }
            if (this.tfWeight.el) {
                this.tfWeight.el.value = this.tfDefaults.tf_weight || 0;
            }
            if (this.tfWeightUnit.el && this.tfDefaults.tf_weight_unit) {
                this.tfWeightUnit.el.value = this.tfDefaults.tf_weight_unit;
            }
        });
    },

    async _onGenerate() {
        let count;
        let qtyToProcess;
        if (this.props.move.data.has_tracking === "lot") {
            count = parseFloat(this.nextSerialCount.el?.value || "0");
            qtyToProcess = parseFloat(this.totalReceived.el?.value || this.props.move.data.product_qty);
        } else {
            count = parseInteger(this.nextSerialCount.el?.value || "0");
            qtyToProcess = this.props.move.data.product_qty;
        }

        const currentLineIds = (this.props.move.data.move_line_ids?.records || [])
            .map((record) => record.resId)
            .filter((id) => Boolean(id));

        const move_line_vals = await this.orm.call("stock.move", "action_generate_lot_line_vals", [{
            ...this.props.move.context,
            default_product_id: this.props.move.data.product_id.id,
            default_location_dest_id: this.props.move.data.location_dest_id.id,
            default_location_id: this.props.move.data.location_id.id,
            default_tracking: this.props.move.data.has_tracking,
            default_quantity: qtyToProcess,
            default_tf_template_move_line_ids: currentLineIds.length ? currentLineIds : (this.tfDefaults.template_move_line_ids || []),
            default_tf_length: parseFloat(this.tfLength.el?.value || "0"),
            default_tf_width: parseFloat(this.tfWidth.el?.value || "0"),
            default_tf_height: parseFloat(this.tfHeight.el?.value || "0"),
            default_tf_dimension_unit: this.tfDimensionUnit.el?.value || false,
            default_tf_weight: parseFloat(this.tfWeight.el?.value || "0"),
            default_tf_weight_unit: this.tfWeightUnit.el?.value || false,
        },
        this.props.mode,
        this.nextSerial.el?.value,
        count,
        this.lots.el?.value,
        ]);

        const newlines = [];
        const lines = this.props.move.data.move_line_ids;
        for (const values of move_line_vals) {
            newlines.push(
                lines._createRecordDatapoint(values, {
                    mode: "readonly",
                    virtualId: getId("virtual"),
                    manuallyAdded: false,
                })
            );
        }

        await lines._applyCommands(lines._currentIds.map((currentId) => [
            x2ManyCommands.DELETE,
            currentId,
        ]));
        lines.records.push(...newlines);
        lines._commands.push(...newlines.map((record) => [
            x2ManyCommands.CREATE,
            record._virtualId,
        ]));
        lines._currentIds.push(...newlines.map((record) => record._virtualId));
        await lines._onUpdate();
        this.props.close();
    },
});
