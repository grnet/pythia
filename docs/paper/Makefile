
.SUFFIXES:.eps .pdf .gz .data .dot

pythia.pdf: pythia.tex pythia.bib
	pdflatex pythia
	bibtex pythia
	pdflatex pythia
	pdflatex pythia

clean:
	rm -f pythia.aux pythia.out pythia.bbl pythia.blg pythia.log pythia.pdf *.swp
