import { BehaviorSubject } from 'rxjs/BehaviorSubject';
import { Subscription } from 'rxjs/Subscription';
import { SearchResults, SearchResult } from './results.model';
import { SearchService } from './search.service';

// TODO: Make this generic TOB client?
//      Neesd refactor
export abstract class SearchClient<T> {
  public result: SearchResult<T>;
  public results: SearchResults<T>;
  public error: any;
  public method;

  private _loading: boolean = false;
  private _params: { [key: string]: any } = {};
  private _search: Subscription;
  private _statusUpdate: BehaviorSubject<boolean> = new BehaviorSubject<boolean>(false);

  constructor(
    protected _service : SearchService,
  ) {}

  get loading(): boolean {
    return this._loading;
  }

  get params() {
    return this._params;
  }

  set params(params: { [key: string]: any }) {
    this._params = Object.assign({}, params);
  }

  get pageNum() {
    return parseInt(this._params['page']) || 0;
  }

  set pageNum(val: number) {
    this._params['page'] = val || 0;
  }

  init() {
    this._params = {};
    this.results = null;
  }

  updateParams(params: { [key: string]: any }) {
    this._params = Object.assign({}, this._params, params);
  }

  // TODO: This is weird here. We should have a better interface.
  getById(id: number) {
    this._loading = true;
    this._service.getById(this.method, id)
      .subscribe(
        this._returnResult.bind(this),
        this._returnError.bind(this),
        this._searchUpdated.bind(this));
  }

  performSearch() {
    this.pageNum = 0;
    this.updateSearch();
  }

  updateSearch() {
    this.cancelSearch();
    this._loading = true;
    this._searchUpdated();
    this._search = this._service.performSearch(this.searchParams)
      .subscribe(
        this._returnResults.bind(this),
        this._returnError.bind(this),
        this._searchUpdated.bind(this));
  }

  clearSearch() {
    this.cancelSearch();
    this.results = null;
    this._searchUpdated();
  }

  get searchParams(): any {
    let p = Object.assign({}, this._params);
    if(! p.method && this.method) p.method = this.method;
    return p;
  }

  cancelSearch() {
    if(this._search) {
      this._search.unsubscribe();
      this._search = null;
      this._loading = false;
      this._searchUpdated();
    }
  }

  nextPage() {
  }

  previousPage() {
  }

  private _returnResults(results: SearchResults<any>) {
    this.results = new SearchResults(
      results.info,
      this.loadResults(results.rows));
    this._loading = false;
  }

  private _returnResult(result: SearchResult<any>) {
    this.result = new SearchResult(
      result.info,
      this.loadSingleResult(result.data));
    this._loading = false;
  }

  loadResults(results: any[]): T[] {
    return results.map(this.loadResult, this);
  }

  loadSingleResult(result: any): T {
    return this.loadResult(result)
  }

  abstract loadResult(result: any): T;

  private _returnError(err: any) {
    console.error('got error: ', err);
    this._loading = false;
  }

  private _searchUpdated() {
    this._statusUpdate.next(this._loading);
  }

  subscribe(proc) {
    return this._statusUpdate.subscribe(proc);
  }
}
