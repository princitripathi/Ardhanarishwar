# RAG Sample Documents

**All files in this folder are SAMPLE DATA FOR TESTING ONLY.**

- They contain synthetic content marked with `# SAMPLE DATA - FOR TESTING ONLY`
- They do NOT represent real company information.
- Purpose: verify RAG ingestion, chunking, embedding, retrieval, and context injection.

Files:
- `SAMPLE_company_policy.txt` — synthetic HR/leave/remote policy
- `SAMPLE_product_faq.txt` — synthetic product FAQ

These are loaded in tests via `app.rag.ingestion.ingest_document`. Not auto-loaded in production; ingestion is explicit.
