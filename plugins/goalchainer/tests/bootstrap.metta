; Register the host OmegaClaw-Core checkout as a PeTTa library path, so the
; core modules this suite imports resolve.
;
; PeTTa's library/3 resolves a two-argument (library X Y) import against a
; registered library_path, and git-import! is what asserts one. On an existing
; directory it registers and returns without cloning or touching the network,
; which is also how the agent bootstraps itself (run.metta). Before PeTTa
; 72a10ef the import resolved against <PeTTa>/lib/../X and needed no
; registration.
;
; The base is the parent of the host checkout, so run.sh runs the suite from the
; OmegaClaw-Core root that this plugin is installed into. It has to be absolute:
; a relative library_path makes library/3 hand back a relative file, and a .py
; import then resolves against the entry file's directory rather than the
; working directory. py-call resolves exactly one dot, so os.path is reached as
; posixpath.
!(import! &self (library lib_import))
!(git-import! "https://github.com/asi-alliance/OmegaClaw-Core.git" "" (py-call (posixpath.abspath "..")))
