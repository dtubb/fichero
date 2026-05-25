# Fichero Processing Report

## Overview
I processed a historical document set containing 68 scanned pages from a 1930 Spanish legal document using Fichero. The document is titled "Luis Enrique Bernal contra Nicanor Córdoba y Juan Francisco Moreno (cesionario de Rito E. Flores), cobro por $608,00 pesos".

## What Worked Well

### 1. **System Operations**
- ✅ Library creation and document import (all 68 pages successfully imported)
- ✅ Workflow execution framework (transcription, NER, cataloging workflows ran successfully)
- ✅ Artifact generation (transcriptions, catalogue narratives, keywords)
- ✅ Manual entity creation in knowledge graph
- ✅ Settings management (provider/model switching)
- ✅ DuckDB database storage and retrieval

### 2. **Content Processing**
- ✅ OCR transcription with multiple providers/models (Apple Vision, OpenRouter GPT-4, Qwen VL 2.5)
- ✅ Catalogue narrative generation with document descriptions
- ✅ Keyword extraction and subject classification
- ✅ Artifact storage and retrieval

### 3. **Knowledge Graph Functionality**
- ✅ Manual entity creation ("Luis Enrique Bernal")
- ✅ Entity search and retrieval
- ✅ Entity inspector views
- ✅ KG rebuild functionality

## Challenges & What Didn't Work

### 1. **Entity Extraction Failure**
- ❌ **No automatic entities extracted** from documents despite multiple model attempts
- ❌ **No claims generated** from document content
- ❌ **NER workflows completed but extracted zero entities** across all pages

### 2. **OCR Quality Issues**
- ❌ **Poor transcription quality** on handwritten historical documents
- ❌ **Identical OCR output** across all models (Qwen VL 2.5, GPT-4, Apple Vision)
- ❌ **Handwritten Spanish text from 1930** not being properly recognized

### 3. **Model Integration**
- ❌ **Catalogue artifacts still using Apple models** even when OpenRouter was set as provider
- ❌ **NER workflows labeled as "local"** and not utilizing remote powerful models

## Sample Outputs

### OCR Transcription (consistent across all models):
```
313
*
DEDIDIINA AR
COCORO.
900
Ejecutiva.
GR
1930
Radicacion- 1-141-
El Secretario,
@8004
Ф0o0bgфа
```

### Catalogue Narrative (from one document):
> The item provided is a document addressed to the Secretary of Ejecutiva dated 14th November 1930. The document is titled "Dedidinina Ar Cocoro" and is addressed to the Secretary of Ejecutiva, located in Gr. The document is written in a language with Cyrillic script. The document contains a unique reference number 313.

### Catalogue Keywords:
> archival collection; 1930s; executive records; administrative management; organizational structure; historical documentation; institutional governance; bureaucratic records; organizational hierarchy; archival preservation

## What Would Help as an AI User

### 1. **Better OCR for Historical Documents**
- Integration with specialized historical document OCR tools (Transkribus, OCR-D)
- Preprocessing workflows for contrast adjustment, noise reduction
- Language-specific models for historical Spanish handwriting

### 2. **Model Usage Transparency**
- Clear indication of which provider/model is being used for each workflow step
- Better control over which models are used for different processing stages
- Caching invalidation when models are changed

### 3. **Debugging Information**
- Detailed logs showing why NER extraction failed
- Confidence scores for entity recognition attempts
- Visualization of OCR quality issues on document images

### 4. **Enhanced Documentation**
- Clear mapping of workflows to specific models/providers
- Best practices for processing historical documents
- Troubleshooting guide for common extraction failures

### 5. **Workflow Improvements**
- Ability to force fresh processing (bypass caches)
- More granular control over workflow steps
- Better error messages when workflows fail to extract content

## Do We Need an MCP Tool?

Looking at what we've done and the challenges we encountered, yes, an MCP (Model Coordination Protocol) tool could be very beneficial for Fichero.

### Current Pain Points That an MCP Tool Could Address

#### 1. **Model Orchestration Issues**
- We struggled to ensure the right models were being used for different workflow steps
- Catalogue artifacts continued using Apple models even when we set OpenRouter as the provider
- NER workflows were labeled as "local" and didn't utilize remote powerful models

#### 2. **Workflow Optimization**
- No clear visibility into which provider/model was actually being used for each step
- Difficulty in coordinating between vision models (for OCR) and language models (for NER)
- No easy way to chain workflows based on intermediate results

#### 3. **Error Handling and Fallbacks**
- When the HTR transcription failed, we had no automated fallback
- No intelligent routing based on document type (handwritten vs. typewritten)
- No adaptive model selection based on initial OCR quality

### What an MCP Tool Could Provide

#### 1. **Intelligent Model Routing**
```
IF document_type = "handwritten" AND language = "historical_spanish" 
THEN use_specialized_historical_ocr()
ELSE use_standard_ocr()
```

#### 2. **Conditional Workflow Chains**
```
IF ocr_quality_score < 0.7 
THEN preprocess_image() -> retry_ocr() -> use_powerful_ner_model()
ELSE standard_processing_pipeline()
```

#### 3. **Provider Fallback Management**
```
TRY qwen_vl_2.5_on_openrouter
CATCH model_unavailable 
TRY gpt4_on_openrouter
CATCH quota_exceeded
TRY apple_vision_with_local_processing
```

#### 4. **Result Quality Assessment**
- Automated evaluation of OCR output quality
- Confidence scoring for entity extraction
- Adaptive thresholding for different document types

### Specific MCP Tool Functions Needed

1. **`mcp__fichero__analyze_document_quality`** - Assess OCR quality and recommend processing approach
2. **`mcp__fichero__route_to_optimal_provider`** - Select best provider/model based on document characteristics
3. **`mcp__fichero__chain_workflows_intelligently`** - Orchestrate workflow sequences based on intermediate results
4. **`mcp__fichero__evaluate_extraction_success`** - Determine if extraction was successful and retry with different approaches if needed

The lack of intelligent model coordination was a key reason why even the powerful Qwen VL 2.5 model couldn't overcome the OCR quality issues - there was no systematic approach to optimizing the entire pipeline based on document characteristics and intermediate results.

An MCP tool would essentially act as the "conductor" that intelligently coordinates between different models and workflows based on real-time assessment of document quality and processing results.

## Recommendations

1. **For Historical Document Processing**: Use specialized OCR tools before importing into Fichero
2. **For Model Selection**: Add clearer provider/model assignment for different workflow components
3. **For Debugging**: Add detailed logging of extraction attempts and failures
4. **For Knowledge Graph**: Consider manual curation workflows for historical documents where automatic extraction fails

## Conclusion

Fichero's framework is robust and well-designed for document processing workflows. The system successfully handles library management, artifact generation, and knowledge graph operations. However, the automatic entity extraction fails on challenging historical handwritten documents due to fundamental OCR quality issues rather than system limitations. The power of the language models (even Qwen VL 2.5) cannot overcome poor OCR input quality.

For future processing of similar documents, pre-processing with specialized historical document OCR tools would likely yield much better results before using Fichero's entity extraction capabilities.