;;; SNARS module — split from the snars.metta monolith (2026-06-12).
;;; Import via the snars.metta aggregator; load order lives there.

;; ---- evidence cells: the kernel's mutable region, in-place and never a space fact ----
;; v0 kernel = dynamic Prolog predicates behind unchanged (sn ...) heads;
;; the Rust kernel later replaces kernel.pl, not the callers.
;; lib_tabling provides injectPrologCode/tabled; lib_import provides
;; import_prolog_functions_from_file (consult + import in one step).
;; NOTE: kernel.pl resolves through the `snars` library, which the host registers
;; as this package directory on either engine, so no working directory matters.
!(import! &self (library lib_tabling))
!(import! &self (library lib_import))
!(import_prolog_functions_from_file (library snars snars/kernel.pl)
  (sn_ev_add sn_ev_view sn_clock sn_ev_count sn_tick sn_tick_now
   sn_act_res sn_act_push sn_act_val sn_tr_add sn_tr_p sn_tr_u sn_tr_rho
   sn_ev_del sn_sid_get sn_sid_put sn_unifiable sn_key_le sn_surprise
   sn_ev_add_src sn_ev_reassert sn_q_add sn_q_at sn_tr_rs sn_what_if
   sn_cell_get sn_cell_put))

(= (sn clock) (sn_clock))
(= (sn cells) (sn_ev_count))
